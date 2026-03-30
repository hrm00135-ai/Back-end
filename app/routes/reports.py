from datetime import datetime, date, timedelta
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.notification import LoginSession
from app.models.user import User
from app.models.task import Task
from app.models.attendance import Attendance
from app.models.leave import LeaveRequest, LeaveBalance, LeaveType
from app.models.payroll import SalaryStructure, Payslip, DailyWage
from app.models.audit import SystemLog
from app.utils.system_logger import verify_log_integrity
from app.utils.helpers import success_response, error_response

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


# ============================================================
# DASHBOARD STATS (Admin/SA)
# ============================================================
@reports_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def dashboard():
    """Main dashboard stats for admin panel."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    # Employee stats
    total_employees = User.query.filter_by(role="employee", is_active=True).count()
    total_admins = User.query.filter_by(role="admin", is_active=True).count()
    inactive_users = User.query.filter_by(is_active=False).count()

    # Department breakdown
    dept_query = db.session.query(
        User.department, db.func.count(User.id)
    ).filter(User.is_active == True, User.role == "employee").group_by(User.department).all()
    departments = {dept or "Unassigned": count for dept, count in dept_query}

    # Today's attendance
    today = date.today()
    checked_in = Attendance.query.filter_by(date=today).filter(
        Attendance.check_in_time.isnot(None)
    ).count()
    checked_out = Attendance.query.filter_by(date=today).filter(
        Attendance.check_out_time.isnot(None)
    ).count()
    late_today = Attendance.query.filter_by(date=today, is_late=True).count()

    # Task stats
    tasks_pending = Task.query.filter_by(status="pending").count()
    tasks_in_progress = Task.query.filter_by(status="in_progress").count()
    tasks_completed_today = Task.query.filter(
        Task.status == "completed",
        db.func.date(Task.completed_at) == today
    ).count()
    tasks_overdue = Task.query.filter(
        Task.due_date < today,
        Task.status.in_(["pending", "in_progress"])
    ).count()

    # Leave stats
    pending_leaves = LeaveRequest.query.filter_by(status="pending").count()
    on_leave_today = LeaveRequest.query.filter(
        LeaveRequest.status == "approved",
        LeaveRequest.from_date <= today,
        LeaveRequest.to_date >= today,
    ).count()

    # Payroll stats for current month
    current_month = today.month
    current_year = today.year
    payslips = Payslip.query.filter_by(month=current_month, year=current_year).all()
    payroll_pending = sum(1 for p in payslips if p.payment_status == "pending")
    payroll_paid = sum(1 for p in payslips if p.payment_status == "paid")

    # Pending daily wages
    pending_wages = DailyWage.query.filter_by(payment_status="pending").count()
    pending_wages_amount = round(
        db.session.query(db.func.sum(DailyWage.total_pay)).filter_by(payment_status="pending").scalar() or 0, 2
    )

    return success_response(data={
        "employees": {
            "total": total_employees,
            "admins": total_admins,
            "inactive": inactive_users,
            "departments": departments,
        },
        "attendance_today": {
            "checked_in": checked_in,
            "checked_out": checked_out,
            "late": late_today,
            "not_checked_in": total_employees - checked_in,
            "on_leave": on_leave_today,
        },
        "tasks": {
            "pending": tasks_pending,
            "in_progress": tasks_in_progress,
            "completed_today": tasks_completed_today,
            "overdue": tasks_overdue,
        },
        "leaves": {
            "pending_approval": pending_leaves,
            "on_leave_today": on_leave_today,
        },
        "payroll": {
            "month": current_month,
            "year": current_year,
            "payslips_generated": len(payslips),
            "paid": payroll_paid,
            "pending": payroll_pending,
            "pending_daily_wages": pending_wages,
            "pending_wages_amount": pending_wages_amount,
        },
    })


# ============================================================
# EMPLOYEE REPORT
# ============================================================
@reports_bp.route("/employee/<int:user_id>", methods=["GET"])
@jwt_required()
def employee_report(user_id):
    """Comprehensive report for a single employee."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    target = User.query.get(user_id)
    if not target:
        return error_response("User not found", 404)

    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)

    # Attendance for month
    start = date(year, month, 1)
    end = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)

    attendance = Attendance.query.filter(
        Attendance.user_id == user_id,
        Attendance.date.between(start, end)
    ).all()

    present = sum(1 for a in attendance if a.status == "present")
    half_days = sum(1 for a in attendance if a.status == "half_day")
    absent = sum(1 for a in attendance if a.status == "absent")
    late = sum(1 for a in attendance if a.is_late)
    total_hours = round(sum(a.total_hours or 0 for a in attendance), 2)
    overtime = round(sum(a.overtime_hours or 0 for a in attendance), 2)

    # Leave for month
    leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id == user_id,
        LeaveRequest.status == "approved",
        LeaveRequest.from_date <= end,
        LeaveRequest.to_date >= start,
    ).all()

    # Tasks for month
    tasks = Task.query.filter(
        Task.assigned_to == user_id,
        db.func.date(Task.created_at).between(start, end)
    ).all()
    tasks_completed = sum(1 for t in tasks if t.status == "completed")

    # Payslip
    payslip = Payslip.query.filter_by(user_id=user_id, month=month, year=year).first()

    # Daily wages
    wages = DailyWage.query.filter(
        DailyWage.user_id == user_id,
        DailyWage.date.between(start, end)
    ).all()

    return success_response(data={
        "employee": {
            "id": target.id,
            "employee_id": target.employee_id,
            "name": f"{target.first_name} {target.last_name}",
            "department": target.department,
            "designation": target.designation,
        },
        "period": {"month": month, "year": year},
        "attendance": {
            "present": present,
            "half_days": half_days,
            "absent": absent,
            "late_days": late,
            "total_hours": total_hours,
            "overtime_hours": overtime,
        },
        "leaves": {
            "approved": len(leaves),
            "total_days": sum(l.total_days for l in leaves),
        },
        "tasks": {
            "total_assigned": len(tasks),
            "completed": tasks_completed,
            "completion_rate": round(tasks_completed / len(tasks) * 100, 1) if tasks else 0,
        },
        "payslip": payslip.to_dict() if payslip else None,
        "daily_wages": {
            "total_entries": len(wages),
            "total_earned": round(sum(w.total_pay for w in wages), 2),
            "total_paid": round(sum(w.total_pay for w in wages if w.payment_status == "paid"), 2),
        },
    })


# ============================================================
# ATTENDANCE REPORT
# ============================================================
@reports_bp.route("/attendance", methods=["GET"])
@jwt_required()
def attendance_report():
    """Attendance report across all employees. Query: ?month=3&year=2026"""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)

    start = date(year, month, 1)
    end = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)

    employees = User.query.filter_by(role="employee", is_active=True).all()
    report = []

    for emp in employees:
        records = Attendance.query.filter(
            Attendance.user_id == emp.id,
            Attendance.date.between(start, end)
        ).all()

        report.append({
            "employee_id": emp.employee_id,
            "name": f"{emp.first_name} {emp.last_name}",
            "department": emp.department,
            "present": sum(1 for r in records if r.status == "present"),
            "half_days": sum(1 for r in records if r.status == "half_day"),
            "absent": sum(1 for r in records if r.status == "absent"),
            "late": sum(1 for r in records if r.is_late),
            "total_hours": round(sum(r.total_hours or 0 for r in records), 2),
            "overtime": round(sum(r.overtime_hours or 0 for r in records), 2),
        })

    return success_response(data={"month": month, "year": year, "report": report})


# ============================================================
# LEAVE REPORT
# ============================================================
@reports_bp.route("/leaves", methods=["GET"])
@jwt_required()
def leave_report():
    """Leave balance report for all employees."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    year = request.args.get("year", date.today().year, type=int)
    employees = User.query.filter_by(role="employee", is_active=True).all()
    leave_types = LeaveType.query.filter_by(is_active=True).all()

    report = []
    for emp in employees:
        balances = {}
        for lt in leave_types:
            bal = LeaveBalance.query.filter_by(user_id=emp.id, leave_type_id=lt.id, year=year).first()
            if bal:
                balances[lt.code] = {"used": bal.used, "available": bal.available, "total": bal.total_quota}
            else:
                balances[lt.code] = {"used": 0, "available": lt.annual_quota, "total": lt.annual_quota}

        report.append({
            "employee_id": emp.employee_id,
            "name": f"{emp.first_name} {emp.last_name}",
            "department": emp.department,
            "balances": balances,
        })

    return success_response(data={"year": year, "report": report})


# ============================================================
# PAYROLL REPORT
# ============================================================
@reports_bp.route("/payroll", methods=["GET"])
@jwt_required()
def payroll_report():
    """Payroll report for a month."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)

    payslips = Payslip.query.filter_by(month=month, year=year).all()

    report = []
    for p in payslips:
        report.append({
            "employee_id": p.user.employee_id if p.user else None,
            "name": f"{p.user.first_name} {p.user.last_name}" if p.user else None,
            "gross": p.gross_earnings,
            "deductions": p.total_deductions,
            "net_pay": p.net_pay,
            "bonus": p.bonus,
            "overtime_pay": p.overtime_pay,
            "payment_status": p.payment_status,
            "payment_date": p.payment_date.isoformat() if p.payment_date else None,
        })

    total_gross = round(sum(p.gross_earnings for p in payslips), 2)
    total_net = round(sum(p.net_pay for p in payslips), 2)

    return success_response(data={
        "month": month, "year": year,
        "total_employees": len(payslips),
        "total_gross": total_gross,
        "total_net": total_net,
        "report": report,
    })


# ============================================================
# SYSTEM LOGS (Super Admin ONLY - hidden from all other roles)
# ============================================================
@reports_bp.route("/system-logs", methods=["GET"])
@jwt_required()
def get_system_logs():
    """View system logs. Super Admin only."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role != "super_admin":
        return error_response("Access denied", 403)

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    action = request.args.get("action")
    user_id = request.args.get("user_id")
    resource = request.args.get("resource")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    query = SystemLog.query

    if action:
        query = query.filter_by(action=action)
    if user_id:
        query = query.filter_by(user_id=int(user_id))
    if resource:
        query = query.filter_by(resource=resource)
    if from_date:
        try:
            query = query.filter(SystemLog.created_at >= datetime.strptime(from_date, "%Y-%m-%d"))
        except ValueError:
            pass
    if to_date:
        try:
            query = query.filter(SystemLog.created_at <= datetime.strptime(to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass

    pagination = query.order_by(SystemLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return success_response(data={
        "logs": [l.to_dict() for l in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })


# ============================================================
# VERIFY LOG INTEGRITY (Super Admin ONLY)
# ============================================================
@reports_bp.route("/system-logs/verify", methods=["GET"])
@jwt_required()
def verify_logs():
    """Verify that system logs haven't been tampered with."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role != "super_admin":
        return error_response("Access denied", 403)

    result = verify_log_integrity()
    return success_response(data=result)


# ============================================================
# LOGIN HISTORY REPORT
# ============================================================
@reports_bp.route("/login-history", methods=["GET"])
@jwt_required()
def login_history():
    """Login history report. Admin sees employees, Super Admin sees all."""
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

    result = []
    for s in sessions:
        user = User.query.get(s.user_id)
        result.append({
            "employee_id": user.employee_id,
            "name": f"{user.first_name} {user.last_name}",
            "role": user.role,
            "login_time": s.login_time.isoformat() if s.login_time else None,
            "logout_time": s.logout_time.isoformat() if s.logout_time else None,
            "ip_address": s.ip_address,
            "device": s.user_agent,
            "status": "Active" if s.is_active else "Logged Out",
            "forced_logout": s.forced_logout,
        })

    return success_response(data=result)


# ============================================================
# ACTIVE USERS (WHO IS ONLINE)
# ============================================================
@reports_bp.route("/active-users", methods=["GET"])
@jwt_required()
def active_users():
    """Currently logged-in users."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Insufficient permissions", 403)

    query = LoginSession.query.filter_by(is_active=True).join(
        User, LoginSession.user_id == User.id
    )

    if current_user.role == "admin":
        query = query.filter(User.role == "employee")

    sessions = query.order_by(LoginSession.login_time.desc()).all()

    result = []
    for s in sessions:
        user = User.query.get(s.user_id)
        result.append({
            "employee_id": user.employee_id,
            "name": f"{user.first_name} {user.last_name}",
            "login_time": s.login_time.isoformat(),
            "ip_address": s.ip_address,
            "device": s.user_agent,
        })

    return success_response(data=result)