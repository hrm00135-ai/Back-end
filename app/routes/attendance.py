from datetime import datetime, date, timedelta
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.user import User
from app.models.attendance import Attendance, AttendanceConfig
from app.utils.helpers import log_audit, success_response, error_response

attendance_bp = Blueprint("attendance", __name__, url_prefix="/api/attendance")


def get_default_config():
    """Get or create default attendance config."""
    config = AttendanceConfig.query.filter_by(name="Default").first()
    if not config:
        config = AttendanceConfig(name="Default")
        db.session.add(config)
        db.session.commit()
    return config


# ============================================================
# CHECK IN
# ============================================================
@attendance_bp.route("/check-in", methods=["POST"])
@jwt_required()
def check_in():
    """
    Employee checks in for the day.
    Body: { "lat": 19.076, "lng": 72.877, "address": "Mumbai Workshop" } (all optional)
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    today = date.today()

    # Check if already checked in today
    existing = Attendance.query.filter_by(user_id=current_user_id, date=today).first()
    if existing and existing.check_in_time:
        return error_response(
            f"Already checked in today at {existing.check_in_time.strftime('%I:%M %p')}",
            400
        )

    data = request.get_json(silent=True) or {}
    now = datetime.utcnow()

    if existing:
        # Record exists (e.g., marked absent by admin), update it
        existing.check_in_time = now
        existing.check_in_lat = data.get("lat")
        existing.check_in_lng = data.get("lng")
        existing.check_in_address = data.get("address", "").strip() or None
        existing.status = "present"
        record = existing
    else:
        record = Attendance(
            user_id=current_user_id,
            date=today,
            check_in_time=now,
            check_in_lat=data.get("lat"),
            check_in_lng=data.get("lng"),
            check_in_address=data.get("address", "").strip() or None,
            status="present",
        )
        db.session.add(record)

    # Check if late
    config = get_default_config()
    shift_start_dt = datetime.combine(today, config.shift_start)
    grace_dt = shift_start_dt + timedelta(minutes=config.late_threshold_minutes)

    if now > grace_dt:
        record.is_late = True
        record.late_minutes = int((now - shift_start_dt).total_seconds() / 60)

    db.session.commit()

    log_audit(current_user_id, "CHECK_IN", details={
        "time": now.isoformat(),
        "is_late": record.is_late,
        "lat": data.get("lat"),
        "lng": data.get("lng"),
    })

    return success_response(
        data=record.to_dict(),
        message=f"Checked in at {now.strftime('%I:%M %p')}" + (" (Late)" if record.is_late else "")
    )


# ============================================================
# CHECK OUT
# ============================================================
@attendance_bp.route("/check-out", methods=["POST"])
@jwt_required()
def check_out():
    """
    Employee checks out.
    Body: { "lat": 19.076, "lng": 72.877, "address": "Mumbai Workshop" } (optional)
    """
    current_user_id = int(get_jwt_identity())
    today = date.today()

    record = Attendance.query.filter_by(user_id=current_user_id, date=today).first()

    if not record or not record.check_in_time:
        return error_response("You haven't checked in today", 400)

    if record.check_out_time:
        return error_response(
            f"Already checked out at {record.check_out_time.strftime('%I:%M %p')}",
            400
        )

    data = request.get_json(silent=True) or {}
    now = datetime.utcnow()

    record.check_out_time = now
    record.check_out_lat = data.get("lat")
    record.check_out_lng = data.get("lng")
    record.check_out_address = data.get("address", "").strip() or None

    # Calculate hours
    config = get_default_config()
    record.calculate_hours(config)

    db.session.commit()

    log_audit(current_user_id, "CHECK_OUT", details={
        "time": now.isoformat(),
        "total_hours": record.total_hours,
        "overtime": record.overtime_hours,
    })

    return success_response(
        data=record.to_dict(),
        message=f"Checked out at {now.strftime('%I:%M %p')}. Total: {record.total_hours}h"
    )


# ============================================================
# MY ATTENDANCE TODAY
# ============================================================
@attendance_bp.route("/today", methods=["GET"])
@jwt_required()
def my_today():
    """Get current user's attendance for today."""
    current_user_id = int(get_jwt_identity())
    today = date.today()

    record = Attendance.query.filter_by(user_id=current_user_id, date=today).first()

    if not record:
        return success_response(data=None, message="No attendance record for today")

    return success_response(data=record.to_dict())


# ============================================================
# MY ATTENDANCE HISTORY
# ============================================================
@attendance_bp.route("/my-history", methods=["GET"])
@jwt_required()
def my_history():
    """Get current user's attendance history with optional date range."""
    current_user_id = int(get_jwt_identity())

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 31, type=int)

    query = Attendance.query.filter_by(user_id=current_user_id)

    if from_date:
        try:
            query = query.filter(Attendance.date >= datetime.strptime(from_date, "%Y-%m-%d").date())
        except ValueError:
            return error_response("Invalid from_date format", 400)
    if to_date:
        try:
            query = query.filter(Attendance.date <= datetime.strptime(to_date, "%Y-%m-%d").date())
        except ValueError:
            return error_response("Invalid to_date format", 400)

    pagination = query.order_by(Attendance.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return success_response(data={
        "records": [r.to_dict() for r in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })


# ============================================================
# VIEW EMPLOYEE ATTENDANCE (Admin/Super Admin)
# ============================================================
@attendance_bp.route("/employee/<int:user_id>", methods=["GET"])
@jwt_required()
def employee_attendance(user_id):
    """View attendance for a specific employee. Admin/Super Admin only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    target = User.query.get(user_id)
    if not target:
        return error_response("User not found", 404)

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    month = request.args.get("month")  # Format: 2026-03

    query = Attendance.query.filter_by(user_id=user_id)

    if month:
        try:
            year, mon = map(int, month.split("-"))
            start = date(year, mon, 1)
            if mon == 12:
                end = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end = date(year, mon + 1, 1) - timedelta(days=1)
            query = query.filter(Attendance.date.between(start, end))
        except (ValueError, IndexError):
            return error_response("Invalid month format. Use YYYY-MM", 400)
    else:
        if from_date:
            try:
                query = query.filter(Attendance.date >= datetime.strptime(from_date, "%Y-%m-%d").date())
            except ValueError:
                pass
        if to_date:
            try:
                query = query.filter(Attendance.date <= datetime.strptime(to_date, "%Y-%m-%d").date())
            except ValueError:
                pass

    records = query.order_by(Attendance.date.desc()).all()

    return success_response(data={
        "employee": {
            "id": target.id,
            "employee_id": target.employee_id,
            "name": f"{target.first_name} {target.last_name}",
        },
        "records": [r.to_dict() for r in records],
        "total_records": len(records),
    })


# ============================================================
# ADMIN OVERRIDE ATTENDANCE
# ============================================================
@attendance_bp.route("/override/<int:record_id>", methods=["PUT"])
@jwt_required()
def override_attendance(record_id):
    """
    Admin manually edits attendance record.
    Body: { "check_in_time", "check_out_time", "status", "reason" }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    record = Attendance.query.get(record_id)
    if not record:
        return error_response("Attendance record not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    if not data.get("reason", "").strip():
        return error_response("Reason is required for manual override", 400)

    # Update fields
    if "check_in_time" in data and data["check_in_time"]:
        try:
            record.check_in_time = datetime.fromisoformat(data["check_in_time"])
        except ValueError:
            return error_response("Invalid check_in_time format. Use ISO format", 400)

    if "check_out_time" in data and data["check_out_time"]:
        try:
            record.check_out_time = datetime.fromisoformat(data["check_out_time"])
        except ValueError:
            return error_response("Invalid check_out_time format. Use ISO format", 400)

    if "status" in data:
        record.status = data["status"]

    if "notes" in data:
        record.notes = data["notes"].strip() or None

    # Recalculate hours if both times present
    if record.check_in_time and record.check_out_time:
        config = get_default_config()
        record.calculate_hours(config)

    record.is_manually_edited = True
    record.edited_by = current_user_id
    record.edit_reason = data["reason"].strip()

    db.session.commit()

    log_audit(current_user_id, "ATTENDANCE_OVERRIDE", target_user_id=record.user_id,
              details={"record_id": record_id, "reason": data["reason"]})

    return success_response(data=record.to_dict(), message="Attendance record updated")


# ============================================================
# MARK ABSENT (Admin - for employees who didn't check in)
# ============================================================
@attendance_bp.route("/mark-absent", methods=["POST"])
@jwt_required()
def mark_absent():
    """
    Admin marks an employee as absent for a specific date.
    Body: { "user_id": 3, "date": "2026-03-22", "notes": "No show" }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    user_id = data.get("user_id")
    target_date = data.get("date")

    if not user_id or not target_date:
        return error_response("user_id and date are required", 400)

    try:
        target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return error_response("Invalid date format", 400)

    target = User.query.get(int(user_id))
    if not target:
        return error_response("User not found", 404)

    # Check if record already exists
    existing = Attendance.query.filter_by(user_id=int(user_id), date=target_date).first()
    if existing:
        return error_response(f"Record already exists for {target_date} with status: {existing.status}", 400)

    record = Attendance(
        user_id=int(user_id),
        date=target_date,
        status="absent",
        notes=data.get("notes", "").strip() or None,
        is_manually_edited=True,
        edited_by=current_user_id,
        edit_reason="Marked absent by admin",
    )
    db.session.add(record)
    db.session.commit()

    log_audit(current_user_id, "MARK_ABSENT", target_user_id=int(user_id),
              details={"date": target_date.isoformat()})

    return success_response(data=record.to_dict(), message=f"Marked {target.employee_id} absent for {target_date}")


# ============================================================
# MONTHLY SUMMARY (Admin)
# ============================================================
@attendance_bp.route("/summary/<int:user_id>", methods=["GET"])
@jwt_required()
def monthly_summary(user_id):
    """
    Monthly attendance summary for an employee.
    Query param: month=2026-03
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    # Employee can see own summary
    if current_user.role == "employee" and current_user_id != user_id:
        return error_response("Insufficient permissions", 403)
    if current_user.role == "admin" and current_user_id != user_id:
        target = User.query.get(user_id)
        if not target or target.role != "employee":
            return error_response("Insufficient permissions", 403)

    month_str = request.args.get("month")
    if not month_str:
        month_str = date.today().strftime("%Y-%m")

    try:
        year, mon = map(int, month_str.split("-"))
        start = date(year, mon, 1)
        if mon == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, mon + 1, 1) - timedelta(days=1)
    except (ValueError, IndexError):
        return error_response("Invalid month format. Use YYYY-MM", 400)

    records = Attendance.query.filter(
        Attendance.user_id == user_id,
        Attendance.date.between(start, end)
    ).all()

    target = User.query.get(user_id)

    present = sum(1 for r in records if r.status == "present")
    half_days = sum(1 for r in records if r.status == "half_day")
    absent = sum(1 for r in records if r.status == "absent")
    on_leave = sum(1 for r in records if r.status == "on_leave")
    late_days = sum(1 for r in records if r.is_late)
    total_hours = round(sum(r.total_hours or 0 for r in records), 2)
    overtime_hours = round(sum(r.overtime_hours or 0 for r in records), 2)
    total_late_minutes = sum(r.late_minutes or 0 for r in records)

    return success_response(data={
        "employee": {
            "id": target.id,
            "employee_id": target.employee_id,
            "name": f"{target.first_name} {target.last_name}",
        },
        "month": month_str,
        "summary": {
            "present": present,
            "half_days": half_days,
            "absent": absent,
            "on_leave": on_leave,
            "late_days": late_days,
            "total_hours": total_hours,
            "overtime_hours": overtime_hours,
            "total_late_minutes": total_late_minutes,
            "working_days": present + half_days,
        }
    })


# ============================================================
# ATTENDANCE CONFIG (Super Admin)
# ============================================================
@attendance_bp.route("/config", methods=["GET"])
@jwt_required()
def get_config():
    """Get attendance configuration."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    config = get_default_config()
    return success_response(data=config.to_dict())


@attendance_bp.route("/config", methods=["PUT"])
@jwt_required()
def update_config():
    """Update attendance configuration. Super Admin only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role != "super_admin":
        return error_response("Only Super Admin can update config", 403)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    config = get_default_config()

    if "shift_start" in data:
        try:
            h, m = map(int, data["shift_start"].split(":"))
            from datetime import time as dt_time
            config.shift_start = dt_time(h, m)
        except (ValueError, AttributeError):
            return error_response("Invalid shift_start format. Use HH:MM", 400)

    if "shift_end" in data:
        try:
            h, m = map(int, data["shift_end"].split(":"))
            from datetime import time as dt_time
            config.shift_end = dt_time(h, m)
        except (ValueError, AttributeError):
            return error_response("Invalid shift_end format. Use HH:MM", 400)

    simple_fields = ["late_threshold_minutes", "half_day_threshold_hours",
                     "full_day_threshold_hours", "overtime_after_hours"]
    for field in simple_fields:
        if field in data:
            setattr(config, field, data[field])

    db.session.commit()

    log_audit(current_user_id, "UPDATE_ATTENDANCE_CONFIG", details=data)

    return success_response(data=config.to_dict(), message="Config updated")