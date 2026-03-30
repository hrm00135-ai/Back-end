from datetime import datetime, timedelta, date
from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from flask_mail import Message as MailMessage
from app.extensions import db, mail
from app.models.user import User
from app.models.auth import RefreshToken, OTPRequest, AuditLog
from app.models.notification import LoginSession
from app.utils.helpers import (
    verify_password,
    hash_password,
    generate_otp,
    hash_otp,
    verify_otp,
    require_role,
    log_audit,
    success_response,
    error_response,
)
from config import Config

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ============================================================
# LOGIN
# ============================================================
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Login for all roles.
    Body: { "email": "...", "password": "..." }
    Returns: access_token, refresh_token, user info
    """
    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return error_response("Email and password are required", 400)

    user = User.query.filter_by(email=email).first()

    if not user:
        return error_response("Invalid email or password", 401)

    if not user.is_active:
        return error_response("Account is deactivated. Contact your administrator.", 403)

    # Check if account is locked
    if user.is_locked:
        lock_duration = timedelta(minutes=Config.ACCOUNT_LOCK_DURATION_MINUTES)
        if user.locked_at and (datetime.utcnow() - user.locked_at) < lock_duration:
            remaining = lock_duration - (datetime.utcnow() - user.locked_at)
            mins = int(remaining.total_seconds() // 60)
            return error_response(
                f"Account is locked. Try again in {mins} minutes or contact your administrator.",
                423,
            )
        else:
            # Auto-unlock after cooldown
            user.is_locked = False
            user.failed_login_attempts = 0
            user.locked_at = None
            db.session.commit()

    # Verify password
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= Config.MAX_FAILED_LOGIN_ATTEMPTS:
            user.is_locked = True
            user.locked_at = datetime.utcnow()
            db.session.commit()
            log_audit(user.id, "ACCOUNT_LOCKED", details={"reason": "Max failed login attempts"})
            return error_response(
                "Account locked due to too many failed attempts. Contact your administrator.",
                423,
            )

        db.session.commit()
        log_audit(user.id, "FAILED_LOGIN", details={"attempt": user.failed_login_attempts})
        remaining = Config.MAX_FAILED_LOGIN_ATTEMPTS - user.failed_login_attempts
        return error_response(
            f"Invalid email or password. {remaining} attempts remaining.", 401
        )

    # Successful login - reset failed attempts
    user.failed_login_attempts = 0
    user.is_locked = False
    user.locked_at = None
    db.session.commit()

    # ── Single-session enforcement (#10): force-logout all previous active sessions ──
    active_sessions = LoginSession.query.filter_by(
        user_id=user.id, is_active=True
    ).all()
    for s in active_sessions:
        s.is_active = False
        s.logout_time = datetime.utcnow()
        s.forced_logout = True
    
    # Revoke all previous refresh tokens
    RefreshToken.query.filter_by(
        user_id=user.id, is_revoked=False
    ).update({"is_revoked": True})
    db.session.commit()

    # Generate tokens
    access_token = create_access_token(identity=str(user.id))
    refresh_token_str = create_refresh_token(identity=str(user.id))
    # Store refresh token
    refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=datetime.utcnow() + Config.JWT_REFRESH_TOKEN_EXPIRES,
    )
    db.session.add(refresh_token)

    # ── Track login session (#2, #4) ──
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    ua = request.headers.get("User-Agent", "")[:500]
    session = LoginSession(
        user_id=user.id,
        login_time=datetime.utcnow(),
        ip_address=ip,
        user_agent=ua,
        session_token=refresh_token_str[:100],
        is_active=True,
    )
    db.session.add(session)
    db.session.commit()

    log_audit(user.id, "LOGIN")

    return success_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token_str,
            "user": user.to_dict(),
        },
        message="Login successful",
    )


# ============================================================
# REFRESH TOKEN
# ============================================================
@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """
    Get new access token using refresh token.
    Header: Authorization: Bearer <refresh_token>
    """
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    if not user or not user.is_active:
        return error_response("Invalid user", 401)

    new_access_token = create_access_token(identity=str(user.id))

    return success_response(
        data={"access_token": new_access_token},
        message="Token refreshed",
    )


# ============================================================
# LOGOUT
# ============================================================
@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """
    Revoke refresh token on logout.
    Body: { "refresh_token": "..." }
    """
    current_user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    refresh_token_str = data.get("refresh_token")

    if refresh_token_str:
        token = RefreshToken.query.filter_by(
            token=refresh_token_str, user_id=current_user_id
        ).first()
        if token:
            token.is_revoked = True
            db.session.commit()

    # ── Close active login session ──
    active_session = LoginSession.query.filter_by(
        user_id=int(current_user_id), is_active=True
    ).order_by(LoginSession.login_time.desc()).first()
    if active_session:
        active_session.is_active = False
        active_session.logout_time = datetime.utcnow()
        db.session.commit()

    log_audit(current_user_id, "LOGOUT")
    return success_response(message="Logged out successfully")


# ============================================================
# PASSWORD RESET - Step 1: Request OTP
# ============================================================
@auth_bp.route("/password-reset/request", methods=["POST"])
def request_password_reset():
    """
    Employee/Admin requests password reset. OTP sent to email.
    Body: { "email": "..." }
    """
    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    email = data.get("email", "").strip().lower()
    if not email:
        return error_response("Email is required", 400)

    user = User.query.filter_by(email=email, is_active=True).first()

    if not user:
        # Don't reveal if email exists
        return success_response(message="If the email exists, an OTP has been sent.")

    # Super Admin can only reset via backend
    if user.role == "super_admin":
        return error_response(
            "Super Admin password can only be reset via backend.", 403
        )

    # Generate OTP
    otp = generate_otp()
    otp_hash = hash_otp(otp)

    # Invalidate previous OTPs
    OTPRequest.query.filter_by(
        user_id=user.id, otp_type="password_reset", is_verified=False
    ).update({"is_verified": True})
    db.session.commit()

    # Store OTP
    otp_request = OTPRequest(
        user_id=user.id,
        otp_code=otp_hash,
        otp_type="password_reset",
        expires_at=datetime.utcnow() + timedelta(minutes=Config.OTP_EXPIRY_MINUTES),
    )
    db.session.add(otp_request)
    db.session.commit()

    # Send OTP via email
    try:
        msg = MailMessage(
            subject="JewelCraft HRM - Password Reset OTP",
            recipients=[user.email],
            body=f"Your OTP for password reset is: {otp}\n\nThis OTP expires in {Config.OTP_EXPIRY_MINUTES} minutes.\n\nIf you did not request this, please ignore this email.",
        )
        mail.send(msg)
    except Exception as e:
        # Log but don't fail - in dev, OTP can be checked from logs
        print(f"[EMAIL ERROR] Failed to send OTP to {user.email}: {e}")
        print(f"[DEV OTP] User: {user.email}, OTP: {otp}")

    log_audit(user.id, "PASSWORD_RESET_REQUESTED")

    return success_response(
        message="If the email exists, an OTP has been sent.",
        data={"otp_request_id": otp_request.id},
    )


# ============================================================
# PASSWORD RESET - Step 2: Verify OTP (by the user)
# ============================================================
@auth_bp.route("/password-reset/verify-otp", methods=["POST"])
def verify_reset_otp():
    """
    User enters OTP to verify their identity.
    Body: { "otp_request_id": 1, "otp": "123456" }
    """
    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    otp_request_id = data.get("otp_request_id")
    otp = data.get("otp", "")

    if not otp_request_id or not otp:
        return error_response("OTP request ID and OTP are required", 400)

    otp_req = OTPRequest.query.get(otp_request_id)

    if not otp_req:
        return error_response("Invalid OTP request", 404)

    if otp_req.is_verified:
        return error_response("OTP already used", 400)

    if otp_req.expires_at < datetime.utcnow():
        return error_response("OTP has expired. Request a new one.", 400)

    if not verify_otp(otp, otp_req.otp_code):
        return error_response("Invalid OTP", 400)

    # Mark as verified - now waiting for authority approval
    otp_req.is_verified = True
    db.session.commit()

    log_audit(otp_req.user_id, "OTP_VERIFIED")

    return success_response(
        message="OTP verified. Waiting for administrator approval to reset password.",
        data={"otp_request_id": otp_req.id, "status": "awaiting_approval"},
    )


# ============================================================
# PASSWORD RESET - Step 3: Admin/Super Admin approves
# ============================================================
@auth_bp.route("/password-reset/approve", methods=["POST"])
@jwt_required()
def approve_password_reset():
    """
    Admin approves employee reset. Super Admin approves admin reset.
    Body: { "otp_request_id": 1, "new_password": "..." }
    """
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    otp_request_id = data.get("otp_request_id")
    new_password = data.get("new_password", "")

    if not otp_request_id or not new_password:
        return error_response("OTP request ID and new password are required", 400)

    if len(new_password) < 8:
        return error_response("Password must be at least 8 characters", 400)

    otp_req = OTPRequest.query.get(otp_request_id)
    if not otp_req:
        return error_response("Invalid OTP request", 404)

    if not otp_req.is_verified:
        return error_response("OTP has not been verified yet", 400)

    if otp_req.is_approved:
        return error_response("Reset already approved", 400)

    target_user = User.query.get(otp_req.user_id)
    if not target_user:
        return error_response("Target user not found", 404)

    # Permission check:
    # - Employee reset -> requires Admin or Super Admin
    # - Admin reset -> requires Super Admin only
    if target_user.role == "employee" and current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can approve employee password resets", 403)

    if target_user.role == "admin" and current_user.role != "super_admin":
        return error_response("Only Super Admin can approve admin password resets", 403)

    if target_user.role == "super_admin":
        return error_response("Super Admin password can only be reset via backend", 403)

    # Approve and reset
    otp_req.is_approved = True
    otp_req.approved_by = current_user.id
    target_user.password_hash = hash_password(new_password)
    target_user.failed_login_attempts = 0
    target_user.is_locked = False
    target_user.locked_at = None

    # Revoke all refresh tokens for the target user
    RefreshToken.query.filter_by(user_id=target_user.id, is_revoked=False).update(
        {"is_revoked": True}
    )

    db.session.commit()

    log_audit(
        current_user.id,
        "PASSWORD_RESET_APPROVED",
        target_user_id=target_user.id,
        details={"target_role": target_user.role},
    )

    return success_response(message=f"Password reset approved for {target_user.employee_id}")


# ============================================================
# GET PENDING RESET REQUESTS (for Admin/Super Admin panel)
# ============================================================
@auth_bp.route("/password-reset/pending", methods=["GET"])
@jwt_required()
def get_pending_resets():
    """
    Get pending password reset requests that need approval.
    Admin sees employee requests. Super Admin sees admin + employee requests.
    """
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    query = (
        OTPRequest.query.filter_by(otp_type="password_reset", is_verified=True, is_approved=False)
        .join(User, OTPRequest.user_id == User.id)
    )

    if current_user.role == "admin":
        query = query.filter(User.role == "employee")
    # super_admin sees both admin and employee requests

    pending = query.order_by(OTPRequest.created_at.desc()).all()

    result = []
    for otp_req in pending:
        user = User.query.get(otp_req.user_id)
        result.append({
            "otp_request_id": otp_req.id,
            "user_id": user.id,
            "employee_id": user.employee_id,
            "name": f"{user.first_name} {user.last_name}",
            "email": user.email,
            "role": user.role,
            "requested_at": otp_req.created_at.isoformat(),
        })

    return success_response(data=result)


# ============================================================
# GET CURRENT USER (ME)
# ============================================================
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    """Get current logged-in user's info."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    if not user:
        return error_response("User not found", 404)

    return success_response(data=user.to_dict())


# ============================================================
# UNLOCK ACCOUNT (Admin/Super Admin)
# ============================================================
@auth_bp.route("/unlock/<int:user_id>", methods=["POST"])
@jwt_required()
def unlock_account(user_id):
    """
    Manually unlock a locked account.
    Admin can unlock employees. Super Admin can unlock anyone.
    """
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response("User not found", 404)

    if target_user.role == "admin" and current_user.role != "super_admin":
        return error_response("Only Super Admin can unlock admin accounts", 403)

    target_user.is_locked = False
    target_user.failed_login_attempts = 0
    target_user.locked_at = None
    db.session.commit()

    log_audit(
        current_user.id,
        "ACCOUNT_UNLOCKED",
        target_user_id=target_user.id,
    )

    return success_response(message=f"Account {target_user.employee_id} unlocked")


# ============================================================
# LOGIN ACTIVITY / SESSIONS (#2, #4)
# ============================================================
@auth_bp.route("/sessions", methods=["GET"])
@jwt_required()
def get_login_sessions():
    """
    Get login sessions. Admin sees employees, Super Admin sees all.
    Query: ?date=2026-03-30  (defaults to today)
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    target_date_str = request.args.get("date")
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date format. Use YYYY-MM-DD", 400)
    else:
        target_date = date.today()

    # Build query
    query = db.session.query(LoginSession).join(
        User, LoginSession.user_id == User.id
    ).filter(
        db.func.date(LoginSession.login_time) == target_date,
        User.is_active == True,
    )

    # Admin can only see employees
    if current_user.role == "admin":
        query = query.filter(User.role == "employee")

    sessions = query.order_by(LoginSession.login_time.desc()).all()

    ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")

    session = LoginSession(
        user_id=User.id,
        ip_address=ip,
        user_agent=user_agent,
        status="active"
    )

    db.session.add(session)
    db.session.commit()
    return success_response(data=[s.to_dict() for s in sessions])


# ============================================================
# ACTIVE SESSIONS (who is currently online)
# ============================================================
@auth_bp.route("/sessions/active", methods=["GET"])
@jwt_required()
def get_active_sessions():
    """Get currently active (online) sessions."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    query = LoginSession.query.filter_by(is_active=True).join(
        User, LoginSession.user_id == User.id
    ).filter(User.is_active == True)

    if current_user.role == "admin":
        query = query.filter(User.role == "employee")

    active = query.order_by(LoginSession.login_time.desc()).all()

    return success_response(data=[s.to_dict() for s in active])