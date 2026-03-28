from datetime import datetime, date
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.user import User
from app.models.auth import AuditLog
from app.utils.helpers import (
    hash_password,
    generate_employee_id,
    require_role,
    log_audit,
    success_response,
    error_response,
)

users_bp = Blueprint("users", __name__, url_prefix="/api/users")


# ============================================================
# REGISTER ADMIN (Super Admin only)
# ============================================================
@users_bp.route("/register/admin", methods=["POST"])
@require_role("super_admin")
def register_admin():
    """
    Super Admin registers a new Admin.
    Accepts: application/json  OR  multipart/form-data
    """
    current_user_id = get_jwt_identity()

    # ✅ Accept both JSON and multipart/form-data
    if request.is_json:
        data = request.get_json()
        photo = None
    else:
        data = request.form
        photo = request.files.get("photo")

    if not data:
        return error_response("Request body is required", 400)

    # Validate required fields
    required = ["email", "password", "first_name", "phone"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return error_response(f"Missing required fields: {', '.join(missing)}", 400)

    email = data["email"].strip().lower()
    password = data["password"]

    if len(password) < 8:
        return error_response("Password must be at least 8 characters", 400)

    # Check duplicate email
    if User.query.filter_by(email=email).first():
        return error_response("Email already registered", 409)

    # Generate employee ID
    employee_id = generate_employee_id("admin")

    # Parse date_of_joining
    doj = data.get("date_of_joining")
    if doj:
        try:
            doj = datetime.strptime(doj, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date_of_joining format. Use YYYY-MM-DD", 400)
    else:
        doj = date.today()

    # Handle photo upload
    photo_url = None
    if photo:
        filename = f"uploads/{email}_{photo.filename}"
        photo.save(filename)
        photo_url = filename

    admin = User(
        employee_id=employee_id,
        email=email,
        password_hash=hash_password(password),
        role="admin",
        first_name=data["first_name"].strip(),
        last_name=data.get("last_name", "").strip(),
        phone=data["phone"].strip(),
        photo_url=photo_url,
        alt_phone=data.get("alt_phone", "").strip() or None,
        department=data.get("department", "").strip() or None,
        designation=data.get("designation", "").strip() or None,
        date_of_joining=doj,
        location_of_work=data.get("location_of_work", "").strip() or None,
        registered_by=current_user_id,
    )

    db.session.add(admin)
    db.session.commit()

    log_audit(
        current_user_id,
        "REGISTER_ADMIN",
        target_user_id=admin.id,
        details={"employee_id": employee_id},
    )

    return success_response(
        data=admin.to_dict(),
        message=f"Admin {employee_id} registered successfully",
        status_code=201,
    )


# ============================================================
# REGISTER EMPLOYEE (Admin or Super Admin only)
# ============================================================
@users_bp.route("/register/employee", methods=["POST"])
@require_role("admin", "super_admin")
def register_employee():
    """
    Admin (or Super Admin) registers a new Employee.
    Accepts: application/json  OR  multipart/form-data
    """
    current_user_id = get_jwt_identity()

    # ✅ Accept both JSON and multipart/form-data
    if request.is_json:
        data = request.get_json()
        photo = None
    else:
        data = request.form
        photo = request.files.get("photo")

    if not data:
        return error_response("Request body is required", 400)

    required = ["email", "password", "first_name", "phone"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return error_response(f"Missing required fields: {', '.join(missing)}", 400)

    email = data["email"].strip().lower()
    password = data["password"]

    if len(password) < 8:
        return error_response("Password must be at least 8 characters", 400)

    if User.query.filter_by(email=email).first():
        return error_response("Email already registered", 409)

    employee_id = generate_employee_id("employee")

    doj = data.get("date_of_joining")
    if doj:
        try:
            doj = datetime.strptime(doj, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date_of_joining format. Use YYYY-MM-DD", 400)
    else:
        doj = date.today()

    # Handle photo upload
    photo_url = None
    if photo:
        filename = f"uploads/{email}_{photo.filename}"
        photo.save(filename)
        photo_url = filename

    employee = User(
        employee_id=employee_id,
        email=email,
        password_hash=hash_password(password),
        role="employee",
        first_name=data["first_name"].strip(),
        last_name=data.get("last_name", "").strip(),
        phone=data["phone"].strip(),
        photo_url=photo_url,
        alt_phone=data.get("alt_phone", "").strip() or None,
        department=data.get("department", "").strip() or None,
        designation=data.get("designation", "").strip() or None,
        date_of_joining=doj,
        location_of_work=data.get("location_of_work", "").strip() or None,
        registered_by=current_user_id,
    )

    db.session.add(employee)
    db.session.commit()

    log_audit(
        current_user_id,
        "REGISTER_EMPLOYEE",
        target_user_id=employee.id,
        details={"employee_id": employee_id},
    )

    return success_response(
        data=employee.to_dict(),
        message=f"Employee {employee_id} registered successfully",
        status_code=201,
    )


# ============================================================
# LIST USERS (role-based visibility)
# ============================================================
@users_bp.route("/", methods=["GET"])
@jwt_required()
def list_users():
    """
    Super Admin: sees all users.
    Admin: sees employees only.
    Employee: sees only self.
    """
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    role_filter = request.args.get("role")
    is_active = request.args.get("is_active", "true").lower() == "true"
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    if current_user.role == "employee":
        return success_response(data=[current_user.to_dict()])

    query = User.query.filter_by(is_active=is_active)

    if current_user.role == "admin":
        query = query.filter_by(role="employee")
    elif role_filter and current_user.role == "super_admin":
        query = query.filter_by(role=role_filter)

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return success_response(
        data={
            "users": [u.to_dict() for u in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
            "per_page": pagination.per_page,
        }
    )


# ============================================================
# GET USER BY ID
# ============================================================
@users_bp.route("/<int:user_id>", methods=["GET"])
@jwt_required()
def get_user(user_id):
    """Get user details by ID (role-based access)."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response("User not found", 404)

    if current_user.role == "employee" and current_user.id != target_user.id:
        return error_response("Insufficient permissions", 403)

    if current_user.role == "admin" and target_user.role != "employee" and current_user.id != target_user.id:
        return error_response("Insufficient permissions", 403)

    include_sensitive = current_user.role in ("super_admin", "admin")
    return success_response(data=target_user.to_dict(include_sensitive=include_sensitive))


# ============================================================
# DEACTIVATE USER
# ============================================================
@users_bp.route("/<int:user_id>/deactivate", methods=["POST"])
@jwt_required()
def deactivate_user(user_id):
    """
    Deactivate a user (soft delete).
    Admin can deactivate employees. Super Admin can deactivate admins.
    """
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response("User not found", 404)

    if target_user.id == current_user.id:
        return error_response("Cannot deactivate your own account", 400)

    if target_user.role == "employee" and current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    if target_user.role == "admin" and current_user.role != "super_admin":
        return error_response("Only Super Admin can deactivate admins", 403)

    if target_user.role == "super_admin":
        return error_response("Cannot deactivate Super Admin", 403)

    target_user.is_active = False
    target_user.date_of_leaving = date.today()
    db.session.commit()

    log_audit(current_user_id, "DEACTIVATE_USER", target_user_id=target_user.id)

    return success_response(message=f"User {target_user.employee_id} deactivated")