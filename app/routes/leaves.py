from datetime import datetime, date, timedelta
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.user import User
from app.models.leave import LeaveType, LeaveBalance, LeaveRequest, Holiday
from app.utils.helpers import log_audit, success_response, error_response

leaves_bp = Blueprint("leaves", __name__, url_prefix="/api/leaves")


def seed_default_leave_types():
    """Create default leave types if none exist."""
    if LeaveType.query.count() == 0:
        defaults = [
            LeaveType(name="Casual Leave", code="CL", annual_quota=12, is_paid=True, description="For personal work"),
            LeaveType(name="Sick Leave", code="SL", annual_quota=12, is_paid=True, description="For illness"),
            LeaveType(name="Earned Leave", code="EL", annual_quota=15, is_paid=True, is_carry_forward=True, max_carry_forward=30, min_days_advance=7, description="Planned leave, apply in advance"),
            LeaveType(name="Unpaid Leave", code="UL", annual_quota=0, is_paid=False, description="Leave without pay"),
        ]
        db.session.add_all(defaults)
        db.session.commit()


def get_or_create_balance(user_id, leave_type_id, year=None):
    """Get or create leave balance for user/type/year."""
    if year is None:
        year = date.today().year
    balance = LeaveBalance.query.filter_by(
        user_id=user_id, leave_type_id=leave_type_id, year=year
    ).first()
    if not balance:
        lt = LeaveType.query.get(leave_type_id)
        balance = LeaveBalance(
            user_id=user_id, leave_type_id=leave_type_id,
            year=year, total_quota=lt.annual_quota if lt else 0
        )
        db.session.add(balance)
        db.session.commit()
    return balance


def calculate_days(from_date, to_date, is_half_day=False):
    """Calculate working days between dates (excludes weekends)."""
    if is_half_day:
        return 0.5
    days = 0
    current = from_date
    while current <= to_date:
        if current.weekday() < 6:  # Mon-Sat (0-5)
            # Check if holiday
            holiday = Holiday.query.filter_by(date=current).first()
            if not holiday:
                days += 1
        current += timedelta(days=1)
    return float(days)


# ============================================================
# LEAVE TYPES (Admin/SA manage, all can view)
# ============================================================
@leaves_bp.route("/types", methods=["GET"])
@jwt_required()
def list_leave_types():
    """Get all active leave types."""
    seed_default_leave_types()
    types = LeaveType.query.filter_by(is_active=True).all()
    return success_response(data=[t.to_dict() for t in types])


@leaves_bp.route("/types", methods=["POST"])
@jwt_required()
def create_leave_type():
    """Create a new leave type. Super Admin only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    if not current_user or current_user.role != "super_admin":
        return error_response("Only Super Admin can create leave types", 403)

    data = request.get_json()
    if not data or not data.get("name") or not data.get("code"):
        return error_response("name and code are required", 400)

    if LeaveType.query.filter_by(code=data["code"].upper()).first():
        return error_response("Leave type code already exists", 409)

    lt = LeaveType(
        name=data["name"].strip(),
        code=data["code"].strip().upper(),
        annual_quota=data.get("annual_quota", 0),
        is_paid=data.get("is_paid", True),
        is_carry_forward=data.get("is_carry_forward", False),
        max_carry_forward=data.get("max_carry_forward", 0),
        requires_approval=data.get("requires_approval", True),
        min_days_advance=data.get("min_days_advance", 0),
        description=data.get("description", "").strip() or None,
    )
    db.session.add(lt)
    db.session.commit()

    log_audit(current_user_id, "CREATE_LEAVE_TYPE", details={"name": lt.name, "code": lt.code})
    return success_response(data=lt.to_dict(), message="Leave type created", status_code=201)


@leaves_bp.route("/types/<int:type_id>", methods=["PUT"])
@jwt_required()
def update_leave_type(type_id):
    """Update leave type. Super Admin only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    if not current_user or current_user.role != "super_admin":
        return error_response("Only Super Admin can update leave types", 403)

    lt = LeaveType.query.get(type_id)
    if not lt:
        return error_response("Leave type not found", 404)

    data = request.get_json()
    fields = ["name", "annual_quota", "is_paid", "is_carry_forward", "max_carry_forward",
              "requires_approval", "min_days_advance", "description", "is_active"]
    for f in fields:
        if f in data:
            setattr(lt, f, data[f].strip() if isinstance(data[f], str) else data[f])

    db.session.commit()
    return success_response(data=lt.to_dict(), message="Leave type updated")


# ============================================================
# MY BALANCE
# ============================================================
@leaves_bp.route("/balance", methods=["GET"])
@jwt_required()
def my_balance():
    """Get current user's leave balance for the year."""
    current_user_id = int(get_jwt_identity())
    year = request.args.get("year", date.today().year, type=int)

    seed_default_leave_types()
    types = LeaveType.query.filter_by(is_active=True).all()
    balances = []
    for lt in types:
        bal = get_or_create_balance(current_user_id, lt.id, year)
        balances.append(bal.to_dict())

    return success_response(data={"year": year, "balances": balances})


@leaves_bp.route("/balance/<int:user_id>", methods=["GET"])
@jwt_required()
def user_balance(user_id):
    """Get specific user's leave balance. Admin/SA only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    target = User.query.get(user_id)
    if not target:
        return error_response("User not found", 404)

    year = request.args.get("year", date.today().year, type=int)
    seed_default_leave_types()
    types = LeaveType.query.filter_by(is_active=True).all()
    balances = []
    for lt in types:
        bal = get_or_create_balance(user_id, lt.id, year)
        balances.append(bal.to_dict())

    return success_response(data={
        "employee": {"id": target.id, "employee_id": target.employee_id, "name": f"{target.first_name} {target.last_name}"},
        "year": year,
        "balances": balances,
    })


# ============================================================
# APPLY LEAVE
# ============================================================
@leaves_bp.route("/apply", methods=["POST"])
@jwt_required()
def apply_leave():
    """
    Employee applies for leave.
    Body: { "leave_type_id", "from_date", "to_date", "reason", "is_half_day", "half_day_period" }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    leave_type_id = data.get("leave_type_id")
    from_date_str = data.get("from_date")
    to_date_str = data.get("to_date")
    reason = data.get("reason", "").strip()
    is_half_day = data.get("is_half_day", False)
    half_day_period = data.get("half_day_period")

    if not leave_type_id or not from_date_str or not reason:
        return error_response("leave_type_id, from_date, and reason are required", 400)

    lt = LeaveType.query.get(leave_type_id)
    if not lt or not lt.is_active:
        return error_response("Invalid leave type", 400)

    try:
        from_dt = datetime.strptime(from_date_str, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date_str or from_date_str, "%Y-%m-%d").date()
    except ValueError:
        return error_response("Invalid date format. Use YYYY-MM-DD", 400)

    if to_dt < from_dt:
        return error_response("to_date cannot be before from_date", 400)

    if is_half_day:
        to_dt = from_dt

    # Check advance days
    if lt.min_days_advance > 0:
        days_ahead = (from_dt - date.today()).days
        if days_ahead < lt.min_days_advance:
            return error_response(f"{lt.name} requires at least {lt.min_days_advance} days advance notice", 400)

    # Calculate total days
    total_days = calculate_days(from_dt, to_dt, is_half_day)
    if total_days <= 0:
        return error_response("No working days in the selected range", 400)

    # Check balance (skip for unpaid)
    if lt.annual_quota > 0:
        balance = get_or_create_balance(current_user_id, lt.id, from_dt.year)
        if balance.available < total_days:
            return error_response(f"Insufficient {lt.name} balance. Available: {balance.available}, Requested: {total_days}", 400)

    # Check overlapping leaves
    overlap = LeaveRequest.query.filter(
        LeaveRequest.user_id == current_user_id,
        LeaveRequest.status.in_(["pending", "approved"]),
        LeaveRequest.from_date <= to_dt,
        LeaveRequest.to_date >= from_dt,
    ).first()
    if overlap:
        return error_response(f"Overlapping leave exists ({overlap.from_date} to {overlap.to_date})", 400)

    leave_req = LeaveRequest(
        user_id=current_user_id,
        leave_type_id=leave_type_id,
        from_date=from_dt,
        to_date=to_dt,
        total_days=total_days,
        is_half_day=is_half_day,
        half_day_period=half_day_period if is_half_day else None,
        reason=reason,
        status="pending",
    )
    db.session.add(leave_req)
    db.session.commit()

    log_audit(current_user_id, "APPLY_LEAVE", details={
        "leave_type": lt.code, "from": from_date_str, "to": to_date_str or from_date_str, "days": total_days
    })

    return success_response(data=leave_req.to_dict(), message=f"Leave applied for {total_days} day(s)", status_code=201)


# ============================================================
# MY LEAVES
# ============================================================
@leaves_bp.route("/my-requests", methods=["GET"])
@jwt_required()
def my_requests():
    """Get current user's leave requests."""
    current_user_id = int(get_jwt_identity())

    status = request.args.get("status")
    year = request.args.get("year", date.today().year, type=int)

    query = LeaveRequest.query.filter_by(user_id=current_user_id)
    query = query.filter(db.extract("year", LeaveRequest.from_date) == year)

    if status:
        query = query.filter_by(status=status)

    requests = query.order_by(LeaveRequest.created_at.desc()).all()
    return success_response(data=[r.to_dict() for r in requests])


# ============================================================
# CANCEL LEAVE (by employee)
# ============================================================
@leaves_bp.route("/<int:leave_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_leave(leave_id):
    """Employee cancels their own pending leave."""
    current_user_id = int(get_jwt_identity())

    leave_req = LeaveRequest.query.get(leave_id)
    if not leave_req:
        return error_response("Leave request not found", 404)

    if leave_req.user_id != current_user_id:
        return error_response("Can only cancel your own leave", 403)

    if leave_req.status not in ("pending", "approved"):
        return error_response(f"Cannot cancel leave with status: {leave_req.status}", 400)

    old_status = leave_req.status
    leave_req.status = "cancelled"
    leave_req.updated_at = datetime.utcnow()

    # Restore balance if was approved
    if old_status == "approved":
        balance = LeaveBalance.query.filter_by(
            user_id=current_user_id,
            leave_type_id=leave_req.leave_type_id,
            year=leave_req.from_date.year
        ).first()
        if balance:
            balance.used = max(0, balance.used - leave_req.total_days)

    db.session.commit()
    log_audit(current_user_id, "CANCEL_LEAVE", details={"leave_id": leave_id})
    return success_response(data=leave_req.to_dict(), message="Leave cancelled")


# ============================================================
# PENDING LEAVES (Admin view)
# ============================================================
@leaves_bp.route("/pending", methods=["GET"])
@jwt_required()
def pending_leaves():
    """Get pending leave requests for approval. Admin/SA only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    query = LeaveRequest.query.filter_by(status="pending").join(User, LeaveRequest.user_id == User.id)

    if current_user.role == "admin":
        query = query.filter(User.role == "employee")

    pending = query.order_by(LeaveRequest.created_at.asc()).all()
    return success_response(data=[r.to_dict() for r in pending])


# ============================================================
# APPROVE / REJECT LEAVE
# ============================================================
@leaves_bp.route("/<int:leave_id>/review", methods=["POST"])
@jwt_required()
def review_leave(leave_id):
    """
    Approve or reject a leave request. Admin/SA only.
    Body: { "action": "approve" or "reject", "comment": "..." }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    leave_req = LeaveRequest.query.get(leave_id)
    if not leave_req:
        return error_response("Leave request not found", 404)

    if leave_req.status != "pending":
        return error_response(f"Can only review pending requests. Current status: {leave_req.status}", 400)

    # Admin can only review employee leaves
    target = User.query.get(leave_req.user_id)
    if current_user.role == "admin" and target.role != "employee":
        return error_response("Admins can only review employee leave requests", 403)

    data = request.get_json()
    if not data or data.get("action") not in ("approve", "reject"):
        return error_response("action must be 'approve' or 'reject'", 400)

    action = data["action"]
    comment = data.get("comment", "").strip()

    if action == "approve":
        # Check balance again
        lt = leave_req.leave_type
        if lt.annual_quota > 0:
            balance = get_or_create_balance(leave_req.user_id, lt.id, leave_req.from_date.year)
            if balance.available < leave_req.total_days:
                return error_response(f"Insufficient balance. Available: {balance.available}", 400)
            balance.used += leave_req.total_days

        leave_req.status = "approved"
    else:
        if not comment:
            return error_response("Comment is required when rejecting", 400)
        leave_req.status = "rejected"

    leave_req.reviewed_by = current_user_id
    leave_req.reviewed_at = datetime.utcnow()
    leave_req.review_comment = comment or None

    db.session.commit()

    log_audit(current_user_id, f"LEAVE_{action.upper()}", target_user_id=leave_req.user_id,
              details={"leave_id": leave_id, "days": leave_req.total_days})

    return success_response(data=leave_req.to_dict(), message=f"Leave {action}d")


# ============================================================
# ALL LEAVES (Admin view with filters)
# ============================================================
@leaves_bp.route("/all", methods=["GET"])
@jwt_required()
def all_leaves():
    """List all leave requests. Admin/SA only. Supports filters."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    query = LeaveRequest.query.join(User, LeaveRequest.user_id == User.id)

    if current_user.role == "admin":
        query = query.filter(User.role == "employee")

    status = request.args.get("status")
    if status:
        query = query.filter(LeaveRequest.status == status)

    user_id = request.args.get("user_id")
    if user_id:
        query = query.filter(LeaveRequest.user_id == int(user_id))

    month = request.args.get("month")
    if month:
        try:
            y, m = map(int, month.split("-"))
            start = date(y, m, 1)
            end = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y + 1, 1, 1) - timedelta(days=1)
            query = query.filter(LeaveRequest.from_date <= end, LeaveRequest.to_date >= start)
        except (ValueError, IndexError):
            pass

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = query.order_by(LeaveRequest.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return success_response(data={
        "requests": [r.to_dict() for r in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })


# ============================================================
# HOLIDAYS
# ============================================================
@leaves_bp.route("/holidays", methods=["GET"])
@jwt_required()
def list_holidays():
    """Get holidays for a year."""
    year = request.args.get("year", date.today().year, type=int)
    holidays = Holiday.query.filter_by(year=year).order_by(Holiday.date.asc()).all()
    return success_response(data=[h.to_dict() for h in holidays])


@leaves_bp.route("/holidays", methods=["POST"])
@jwt_required()
def add_holiday():
    """Add a holiday. Admin/SA only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    data = request.get_json()
    if not data or not data.get("name") or not data.get("date"):
        return error_response("name and date are required", 400)

    try:
        h_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    except ValueError:
        return error_response("Invalid date format", 400)

    if Holiday.query.filter_by(date=h_date).first():
        return error_response("Holiday already exists for this date", 409)

    holiday = Holiday(
        name=data["name"].strip(),
        date=h_date,
        is_optional=data.get("is_optional", False),
        year=h_date.year,
    )
    db.session.add(holiday)
    db.session.commit()

    log_audit(current_user_id, "ADD_HOLIDAY", details={"name": holiday.name, "date": data["date"]})
    return success_response(data=holiday.to_dict(), message="Holiday added", status_code=201)


@leaves_bp.route("/holidays/<int:holiday_id>", methods=["DELETE"])
@jwt_required()
def delete_holiday(holiday_id):
    """Delete a holiday. Admin/SA only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    holiday = Holiday.query.get(holiday_id)
    if not holiday:
        return error_response("Holiday not found", 404)

    db.session.delete(holiday)
    db.session.commit()

    log_audit(current_user_id, "DELETE_HOLIDAY", details={"name": holiday.name})
    return success_response(message="Holiday deleted")