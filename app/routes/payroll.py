from datetime import datetime, date, timedelta
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.user import User
from app.models.payroll import SalaryStructure, Payslip
from app.models.attendance import Attendance
from app.models.leave import LeaveRequest
from app.utils.helpers import log_audit, success_response, error_response
from app.models.payroll import SalaryStructure, Payslip, DailyWage


payroll_bp = Blueprint("payroll", __name__, url_prefix="/api/payroll")


# ============================================================
# SET SALARY STRUCTURE (Admin/SA)
# ============================================================
@payroll_bp.route("/salary/<int:user_id>", methods=["POST"])
@jwt_required()
def set_salary(user_id):
    """
    Set or update salary structure for an employee.
    Deactivates previous structure and creates new one.
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can set salary", 403)

    target = User.query.get(user_id)
    if not target:
        return error_response("User not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    if not data.get("basic_salary"):
        return error_response("basic_salary is required", 400)

    # Deactivate previous active structure
    SalaryStructure.query.filter_by(user_id=user_id, is_active=True).update({
        "is_active": False,
        "effective_to": date.today()
    })

    eff_from = data.get("effective_from")
    if eff_from:
        try:
            eff_from = datetime.strptime(eff_from, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid effective_from format", 400)
    else:
        eff_from = date.today()

    ss = SalaryStructure(
        user_id=user_id,
        basic_salary=data.get("basic_salary", 0),
        hra=data.get("hra", 0),
        da=data.get("da", 0),
        conveyance=data.get("conveyance", 0),
        medical_allowance=data.get("medical_allowance", 0),
        special_allowance=data.get("special_allowance", 0),
        other_allowance=data.get("other_allowance", 0),
        pf_employee=data.get("pf_employee", 0),
        pf_employer=data.get("pf_employer", 0),
        esi_employee=data.get("esi_employee", 0),
        esi_employer=data.get("esi_employer", 0),
        professional_tax=data.get("professional_tax", 0),
        tds=data.get("tds", 0),
        other_deduction=data.get("other_deduction", 0),
        effective_from=eff_from,
        created_by=current_user_id,
    )
    ss.calculate()

    db.session.add(ss)
    db.session.commit()

    log_audit(current_user_id, "SET_SALARY", target_user_id=user_id,
              details={"net_salary": ss.net_salary, "ctc": ss.ctc})

    return success_response(data=ss.to_dict(), message="Salary structure set", status_code=201)


# ============================================================
# GET SALARY STRUCTURE
# ============================================================
@payroll_bp.route("/salary/<int:user_id>", methods=["GET"])
@jwt_required()
def get_salary(user_id):
    """Get current active salary structure."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    # Employee can see own salary
    if current_user.role == "employee" and current_user_id != user_id:
        return error_response("Insufficient permissions", 403)

    ss = SalaryStructure.query.filter_by(user_id=user_id, is_active=True).first()
    if not ss:
        return success_response(data=None, message="No salary structure found")

    return success_response(data=ss.to_dict())


# ============================================================
# SALARY HISTORY
# ============================================================
@payroll_bp.route("/salary/<int:user_id>/history", methods=["GET"])
@jwt_required()
def salary_history(user_id):
    """Get salary revision history."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if current_user.role == "employee" and current_user_id != user_id:
        return error_response("Insufficient permissions", 403)

    history = SalaryStructure.query.filter_by(user_id=user_id).order_by(
        SalaryStructure.effective_from.desc()
    ).all()

    return success_response(data=[s.to_dict() for s in history])


# ============================================================
# ADD DAILY WAGE ENTRY
# ============================================================
@payroll_bp.route("/daily-wage", methods=["POST"])
@jwt_required()
def add_daily_wage():
    """
    Add daily wage entry for an employee.
    Supports: per_day_rate, per_hour_rate, or per_piece_rate.
    Body: { "user_id", "date", "per_day_rate" or "hours_worked"+"per_hour_rate" or "pieces_completed"+"per_piece_rate", ... }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can add daily wages", 403)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    user_id = data.get("user_id")
    wage_date = data.get("date")

    if not user_id or not wage_date:
        return error_response("user_id and date are required", 400)

    target = User.query.get(int(user_id))
    if not target:
        return error_response("User not found", 404)

    try:
        wage_date = datetime.strptime(wage_date, "%Y-%m-%d").date()
    except ValueError:
        return error_response("Invalid date format", 400)

    # Check duplicate
    existing = DailyWage.query.filter_by(user_id=int(user_id), date=wage_date).first()
    if existing:
        return error_response(f"Wage entry already exists for {wage_date}", 409)

    wage = DailyWage(
        user_id=int(user_id),
        date=wage_date,
        hours_worked=data.get("hours_worked", 0),
        per_hour_rate=data.get("per_hour_rate", 0),
        per_day_rate=data.get("per_day_rate", 0),
        pieces_completed=data.get("pieces_completed", 0),
        per_piece_rate=data.get("per_piece_rate", 0),
        overtime_hours=data.get("overtime_hours", 0),
        overtime_rate=data.get("overtime_rate", 1.5),
        bonus=data.get("bonus", 0),
        deduction=data.get("deduction", 0),
        notes=data.get("notes", "").strip() or None,
        created_by=current_user_id,
    )
    wage.calculate()

    db.session.add(wage)
    db.session.commit()

    log_audit(current_user_id, "ADD_DAILY_WAGE", target_user_id=int(user_id),
              details={"date": wage_date.isoformat(), "total_pay": wage.total_pay})

    return success_response(data=wage.to_dict(), message="Daily wage added", status_code=201)


# ============================================================
# GET DAILY WAGES FOR EMPLOYEE
# ============================================================
@payroll_bp.route("/daily-wage/<int:user_id>", methods=["GET"])
@jwt_required()
def get_daily_wages(user_id):
    """
    Get daily wage records. Query: ?from_date=2026-03-01&to_date=2026-03-31&status=pending
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if current_user.role == "employee" and current_user_id != user_id:
        return error_response("Insufficient permissions", 403)

    query = DailyWage.query.filter_by(user_id=user_id)

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    status = request.args.get("status")

    if from_date:
        try:
            query = query.filter(DailyWage.date >= datetime.strptime(from_date, "%Y-%m-%d").date())
        except ValueError:
            pass
    if to_date:
        try:
            query = query.filter(DailyWage.date <= datetime.strptime(to_date, "%Y-%m-%d").date())
        except ValueError:
            pass
    if status:
        query = query.filter_by(payment_status=status)

    records = query.order_by(DailyWage.date.desc()).all()

    total_earned = round(sum(w.total_pay for w in records), 2)
    total_paid = round(sum(w.total_pay for w in records if w.payment_status == "paid"), 2)
    total_pending = round(sum(w.total_pay for w in records if w.payment_status == "pending"), 2)

    return success_response(data={
        "records": [w.to_dict() for w in records],
        "total_records": len(records),
        "total_earned": total_earned,
        "total_paid": total_paid,
        "total_pending": total_pending,
    })


# ============================================================
# PAY DAILY WAGES (mark as paid)
# ============================================================
@payroll_bp.route("/daily-wage/pay", methods=["POST"])
@jwt_required()
def pay_daily_wages():
    """
    Mark daily wages as paid. Can pay single or bulk.
    Body: { "wage_ids": [1, 2, 3], "payment_mode": "cash", "payment_ref": "..." }
    OR: { "user_id": 3, "from_date": "2026-03-17", "to_date": "2026-03-22", "payment_mode": "cash" }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can process payments", 403)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    now = datetime.utcnow()
    payment_mode = data.get("payment_mode", "cash")
    payment_ref = data.get("payment_ref", "").strip() or None

    wages = []

    if "wage_ids" in data:
        wages = DailyWage.query.filter(
            DailyWage.id.in_(data["wage_ids"]),
            DailyWage.payment_status == "pending"
        ).all()
    elif "user_id" in data:
        query = DailyWage.query.filter_by(
            user_id=int(data["user_id"]),
            payment_status="pending"
        )
        if data.get("from_date"):
            try:
                query = query.filter(DailyWage.date >= datetime.strptime(data["from_date"], "%Y-%m-%d").date())
            except ValueError:
                pass
        if data.get("to_date"):
            try:
                query = query.filter(DailyWage.date <= datetime.strptime(data["to_date"], "%Y-%m-%d").date())
            except ValueError:
                pass
        wages = query.all()

    if not wages:
        return error_response("No pending wages found", 404)

    total_paid = 0
    for w in wages:
        w.payment_status = "paid"
        w.payment_mode = payment_mode
        w.payment_ref = payment_ref
        w.paid_at = now
        w.paid_by = current_user_id
        total_paid += w.total_pay

    db.session.commit()

    log_audit(current_user_id, "PAY_DAILY_WAGES", details={
        "count": len(wages), "total": round(total_paid, 2), "mode": payment_mode
    })

    return success_response(data={
        "paid_count": len(wages),
        "total_paid": round(total_paid, 2),
        "payment_mode": payment_mode,
    }, message=f"Paid {len(wages)} wage entries totaling Rs. {round(total_paid, 2)}")


# ============================================================
# WEEKLY SUMMARY
# ============================================================
@payroll_bp.route("/weekly-summary/<int:user_id>", methods=["GET"])
@jwt_required()
def weekly_summary(user_id):
    """
    Get weekly wage summary. Query: ?week_start=2026-03-16 (Monday)
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if current_user.role == "employee" and current_user_id != user_id:
        return error_response("Insufficient permissions", 403)

    target = User.query.get(user_id)
    if not target:
        return error_response("User not found", 404)

    week_start_str = request.args.get("week_start")
    if week_start_str:
        try:
            week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid week_start format", 400)
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday

    week_end = week_start + timedelta(days=6)  # Sunday

    wages = DailyWage.query.filter(
        DailyWage.user_id == user_id,
        DailyWage.date.between(week_start, week_end)
    ).order_by(DailyWage.date.asc()).all()

    total_hours = round(sum(w.hours_worked for w in wages), 2)
    total_pieces = sum(w.pieces_completed for w in wages)
    total_earned = round(sum(w.total_pay for w in wages), 2)
    total_overtime = round(sum(w.overtime_pay for w in wages), 2)
    days_worked = len(wages)
    paid = round(sum(w.total_pay for w in wages if w.payment_status == "paid"), 2)
    pending = round(sum(w.total_pay for w in wages if w.payment_status == "pending"), 2)

    return success_response(data={
        "employee": {
            "id": target.id,
            "employee_id": target.employee_id,
            "name": f"{target.first_name} {target.last_name}",
        },
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "days_worked": days_worked,
        "total_hours": total_hours,
        "total_pieces": total_pieces,
        "total_earned": total_earned,
        "total_overtime": total_overtime,
        "total_paid": paid,
        "total_pending": pending,
        "daily_breakdown": [w.to_dict() for w in wages],
    })

# ============================================================
# GENERATE PAYSLIP
# ============================================================
@payroll_bp.route("/generate", methods=["POST"])
@jwt_required()
def generate_payslip():
    """
    Generate monthly payslip for an employee.
    Body: { "user_id": 3, "month": 3, "year": 2026, "bonus": 0, "overtime_pay": 0 }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can generate payslips", 403)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    user_id = data.get("user_id")
    month = data.get("month")
    year = data.get("year")

    if not all([user_id, month, year]):
        return error_response("user_id, month, and year are required", 400)

    target = User.query.get(int(user_id))
    if not target:
        return error_response("User not found", 404)

    # Check duplicate
    existing = Payslip.query.filter_by(user_id=int(user_id), month=month, year=year).first()
    if existing:
        return error_response(f"Payslip already exists for {month}/{year}", 409)

    # Get active salary structure
    ss = SalaryStructure.query.filter_by(user_id=int(user_id), is_active=True).first()
    if not ss:
        return error_response("No active salary structure found for this employee", 400)

    # Get attendance data for the month
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    attendance_records = Attendance.query.filter(
        Attendance.user_id == int(user_id),
        Attendance.date.between(start_date, end_date)
    ).all()

    present_days = sum(1 for a in attendance_records if a.status == "present")
    half_days = sum(1 for a in attendance_records if a.status == "half_day")
    absent_days = sum(1 for a in attendance_records if a.status == "absent")
    overtime_hours = round(sum(a.overtime_hours or 0 for a in attendance_records), 2)

    # Get approved unpaid leaves
    unpaid_leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id == int(user_id),
        LeaveRequest.status == "approved",
        LeaveRequest.from_date <= end_date,
        LeaveRequest.to_date >= start_date,
        LeaveRequest.leave_type_id == 4  # Unpaid Leave
    ).all()
    unpaid_days = sum(l.total_days for l in unpaid_leaves)

    # Calculate working days in month (Mon-Sat)
    working_days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 6:
            working_days += 1
        current += timedelta(days=1)

    # Calculate deductions
    per_day_salary = round(ss.gross_salary / working_days, 2) if working_days > 0 else 0
    leave_deduction = round(unpaid_days * per_day_salary, 2)
    absent_deduction = round(absent_days * per_day_salary, 2)

    # Build payslip
    payslip = Payslip(
        user_id=int(user_id),
        salary_structure_id=ss.id,
        month=month,
        year=year,
        basic_salary=ss.basic_salary,
        hra=ss.hra,
        da=ss.da,
        conveyance=ss.conveyance,
        medical_allowance=ss.medical_allowance,
        special_allowance=ss.special_allowance,
        other_allowance=ss.other_allowance,
        pf_employee=ss.pf_employee,
        esi_employee=ss.esi_employee,
        professional_tax=ss.professional_tax,
        tds=ss.tds,
        other_deduction=ss.other_deduction,
        overtime_pay=data.get("overtime_pay", 0),
        bonus=data.get("bonus", 0),
        leave_deduction=leave_deduction,
        late_deduction=absent_deduction,
        working_days=working_days,
        present_days=present_days + (half_days * 0.5),
        leave_days=sum(l.total_days for l in LeaveRequest.query.filter(
            LeaveRequest.user_id == int(user_id),
            LeaveRequest.status == "approved",
            LeaveRequest.from_date <= end_date,
            LeaveRequest.to_date >= start_date
        ).all()),
        absent_days=absent_days,
        overtime_hours=overtime_hours,
        generated_by=current_user_id,
    )

    # Calculate totals
    payslip.gross_earnings = round(
        ss.gross_salary + payslip.overtime_pay + payslip.bonus, 2
    )
    payslip.total_deductions = round(
        ss.pf_employee + ss.esi_employee + ss.professional_tax + ss.tds +
        ss.other_deduction + leave_deduction + absent_deduction, 2
    )
    payslip.net_pay = round(payslip.gross_earnings - payslip.total_deductions, 2)

    db.session.add(payslip)
    db.session.commit()

    log_audit(current_user_id, "GENERATE_PAYSLIP", target_user_id=int(user_id),
              details={"month": month, "year": year, "net_pay": payslip.net_pay})

    return success_response(data=payslip.to_dict(), message="Payslip generated", status_code=201)


# ============================================================
# GET PAYSLIP
# ============================================================
@payroll_bp.route("/payslip/<int:user_id>", methods=["GET"])
@jwt_required()
def get_payslip(user_id):
    """Get payslip for a specific month. Query: ?month=3&year=2026"""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if current_user.role == "employee" and current_user_id != user_id:
        return error_response("Insufficient permissions", 403)

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)

    if not month or not year:
        return error_response("month and year query params are required", 400)

    payslip = Payslip.query.filter_by(user_id=user_id, month=month, year=year).first()
    if not payslip:
        return error_response(f"No payslip found for {month}/{year}", 404)

    return success_response(data=payslip.to_dict())


# ============================================================
# LIST PAYSLIPS
# ============================================================
@payroll_bp.route("/payslips/<int:user_id>", methods=["GET"])
@jwt_required()
def list_payslips(user_id):
    """List all payslips for an employee. Query: ?year=2026"""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if current_user.role == "employee" and current_user_id != user_id:
        return error_response("Insufficient permissions", 403)

    year = request.args.get("year", date.today().year, type=int)

    payslips = Payslip.query.filter_by(user_id=user_id, year=year).order_by(
        Payslip.month.asc()
    ).all()

    return success_response(data=[p.to_dict() for p in payslips])


# ============================================================
# UPDATE PAYMENT STATUS
# ============================================================
@payroll_bp.route("/payslip/<int:payslip_id>/payment", methods=["PUT"])
@jwt_required()
def update_payment(payslip_id):
    """
    Mark payslip as paid/processed.
    Body: { "status": "paid", "payment_mode": "bank_transfer", "transaction_ref": "TXN123", "payment_date": "2026-03-31" }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can update payment", 403)

    payslip = Payslip.query.get(payslip_id)
    if not payslip:
        return error_response("Payslip not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    if "status" in data:
        payslip.payment_status = data["status"]

    if "payment_mode" in data:
        payslip.payment_mode = data["payment_mode"]

    if "transaction_ref" in data:
        payslip.transaction_ref = data["transaction_ref"]

    if "payment_date" in data and data["payment_date"]:
        try:
            payslip.payment_date = datetime.strptime(data["payment_date"], "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid payment_date format", 400)

    if "payment_notes" in data:
        payslip.payment_notes = data["payment_notes"]

    db.session.commit()

    log_audit(current_user_id, "UPDATE_PAYMENT", target_user_id=payslip.user_id,
              details={"payslip_id": payslip_id, "status": payslip.payment_status})

    return success_response(data=payslip.to_dict(), message="Payment updated")


# ============================================================
# PAYROLL SUMMARY (for admin dashboard)
# ============================================================
@payroll_bp.route("/summary", methods=["GET"])
@jwt_required()
def payroll_summary():
    """Get payroll summary for a month. Query: ?month=3&year=2026"""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)

    payslips = Payslip.query.filter_by(month=month, year=year).all()

    total_gross = round(sum(p.gross_earnings for p in payslips), 2)
    total_deductions = round(sum(p.total_deductions for p in payslips), 2)
    total_net = round(sum(p.net_pay for p in payslips), 2)
    total_pf = round(sum(p.pf_employee for p in payslips), 2)
    total_esi = round(sum(p.esi_employee for p in payslips), 2)
    total_tds = round(sum(p.tds for p in payslips), 2)

    paid = sum(1 for p in payslips if p.payment_status == "paid")
    pending = sum(1 for p in payslips if p.payment_status == "pending")
    processed = sum(1 for p in payslips if p.payment_status == "processed")

    return success_response(data={
        "month": month,
        "year": year,
        "total_employees": len(payslips),
        "total_gross": total_gross,
        "total_deductions": total_deductions,
        "total_net": total_net,
        "total_pf": total_pf,
        "total_esi": total_esi,
        "total_tds": total_tds,
        "payment_status": {
            "paid": paid,
            "pending": pending,
            "processed": processed,
        }
    })