import bcrypt
import random
import string
import json
from datetime import datetime
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.extensions import db
from app.models.user import User
from app.models.auth import AuditLog


# ============================================================
# Password Hashing
# ============================================================

def hash_password(password: str) -> str:
    """Hash password with bcrypt + salt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ============================================================
# OTP Generation
# ============================================================

def generate_otp(length: int = 6) -> str:
    """Generate numeric OTP."""
    return "".join(random.choices(string.digits, k=length))


def hash_otp(otp: str) -> str:
    """Hash OTP with bcrypt."""
    return hash_password(otp)


def verify_otp(otp: str, otp_hash: str) -> bool:
    """Verify OTP against hash."""
    return verify_password(otp, otp_hash)


# ============================================================
# Employee ID Generation
# ============================================================

def generate_employee_id(role: str) -> str:
    """Generate unique employee ID like EMP-001, ADM-001, SA-001."""
    prefix_map = {
        "super_admin": "SA",
        "admin": "ADM",
        "employee": "EMP",
    }
    prefix = prefix_map.get(role, "USR")

    # Find the latest ID for this role
    latest = (
        User.query.filter(User.employee_id.like(f"{prefix}-%"))
        .order_by(User.id.desc())
        .first()
    )

    if latest:
        try:
            last_num = int(latest.employee_id.split("-")[1])
            next_num = last_num + 1
        except (IndexError, ValueError):
            next_num = 1
    else:
        next_num = 1

    return f"{prefix}-{next_num:03d}"


# ============================================================
# Role-Based Access Decorators
# ============================================================

def require_role(*allowed_roles):
    """
    Decorator to restrict route access by role.
    Usage: @require_role('super_admin', 'admin')
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            identity = get_jwt_identity()

            user = User.query.get(identity)
            if not user:
                return jsonify({"error": "User not found"}), 404
            if not user.is_active:
                return jsonify({"error": "Account is deactivated"}), 403
            if user.is_locked:
                return jsonify({"error": "Account is locked"}), 403
            if user.role not in allowed_roles:
                return jsonify({"error": "Insufficient permissions"}), 403

            return fn(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# Audit Logging
# ============================================================

def log_audit(user_id, action, target_user_id=None, details=None, ip_address=None):
    """Create an audit log entry."""
    if ip_address is None:
        ip_address = request.remote_addr if request else None

    log = AuditLog(
        user_id=user_id,
        action=action,
        target_user_id=target_user_id,
        details=json.dumps(details) if isinstance(details, dict) else details,
        ip_address=ip_address,
    )
    db.session.add(log)
    db.session.commit()
    return log


# ============================================================
# Response Helpers
# ============================================================

def success_response(data=None, message="Success", status_code=200):
    response = {"status": "success", "message": message}
    if data is not None:
        response["data"] = data
    return jsonify(response), status_code


def error_response(message="Error", status_code=400, errors=None):
    response = {"status": "error", "message": message}
    if errors:
        response["errors"] = errors
    return jsonify(response), status_code
