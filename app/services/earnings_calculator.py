"""
JewelCraft HRM — Earnings Calculation Service
File: app/services/earnings_calculator.py

Pure-Python, no side-effects. All DB queries are read-only.
Import and call from routes; never call from models.
"""

from datetime import date
from decimal import Decimal
from sqlalchemy import func
from app.models.user       import User
from app.models.attendance import Attendance      
from app.models.task       import Task     

from app.models.payment import (
    EmployeePaymentConfig,
    PaymentTransaction,
    WageType,
    PaymentStatus,
)


def _get_config(user_id: int) -> EmployeePaymentConfig | None:
    """Return the active payment config for a user, or None."""
    return (
        EmployeePaymentConfig.query
        .filter_by(user_id=user_id, is_active=True)
        .order_by(EmployeePaymentConfig.effective_from.desc())
        .first()
    )


def _total_paid(employee_id: int) -> Decimal:
    """Sum all COMPLETED (non-reversed) payments for an employee."""
    result = (
        PaymentTransaction.query
        .with_entities(func.coalesce(func.sum(PaymentTransaction.amount), 0))
        .filter(
            PaymentTransaction.employee_id == employee_id,
            PaymentTransaction.status == PaymentStatus.COMPLETED,
        )
        .scalar()
    )
    return Decimal(str(result))


# ─────────────────────────────────────────────────────────────────────────────
#  Core calculation: total_earned
# ─────────────────────────────────────────────────────────────────────────────

def calculate_earnings(
    employee_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Calculate how much an employee has *earned* based on their wage type.

    Returns a dict:
    {
        "wage_type":          "monthly_salary" | "daily_wage" | "per_task",
        "wage_amount":        float,
        "total_earned":       float,
        "work_summary":       { ... },   # type-specific details
        "from_date":          str | None,
        "to_date":            str | None,
    }
    """

    # Lazy import to avoid circular dependencies — adjust to your actual paths.
    from app.models.attendance import Attendance   # noqa
    from app.models.task import Task               # noqa

    config = _get_config(employee_id)
    if config is None:
        return {
            "wage_type":    None,
            "wage_amount":  0.0,
            "total_earned": 0.0,
            "work_summary": {"error": "No payment config found for this employee"},
            "from_date":    from_date.isoformat() if from_date else None,
            "to_date":      to_date.isoformat() if to_date else None,
        }

    wage = Decimal(str(config.wage_amount))

    # ── MONTHLY SALARY ────────────────────────────────────────────────────────
    if config.wage_type == WageType.MONTHLY_SALARY:
        total_earned, summary = _monthly_salary_earnings(
            employee_id, wage, from_date, to_date
        )

    # ── DAILY WAGE ────────────────────────────────────────────────────────────
    elif config.wage_type == WageType.DAILY_WAGE:
        total_earned, summary = _daily_wage_earnings(
            employee_id, wage, from_date, to_date, Attendance
        )

    # ── PER TASK ──────────────────────────────────────────────────────────────
    elif config.wage_type == WageType.PER_TASK:
        total_earned, summary = _per_task_earnings(
            employee_id, wage, from_date, to_date, Task
        )

    else:
        total_earned, summary = Decimal("0"), {"error": "Unknown wage type"}

    return {
        "wage_type":    config.wage_type.value,
        "wage_amount":  float(wage),
        "total_earned": float(total_earned),
        "work_summary": summary,
        "from_date":    from_date.isoformat() if from_date else None,
        "to_date":      to_date.isoformat() if to_date else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Strategy helpers
# ─────────────────────────────────────────────────────────────────────────────

def _monthly_salary_earnings(
    employee_id: int,
    monthly_wage: Decimal,
    from_date: date | None,
    to_date: date | None,
) -> tuple[Decimal, dict]:
    """
    Earnings = monthly_wage × number_of_full_months_worked.
    If no date range is supplied, we count full months from the
    employee's effective_from date to today.
    """
    from calendar import monthrange
    from app.models.payment import EmployeePaymentConfig

    config = _get_config(employee_id)
    start  = from_date or (config.effective_from if config else date.today())
    end    = to_date   or date.today()

    # Count distinct (year, month) pairs in the range
    months = _count_months(start, end)

    total_earned = monthly_wage * Decimal(str(months))
    summary = {
        "months_worked":   months,
        "monthly_rate":    float(monthly_wage),
        "period_start":    start.isoformat(),
        "period_end":      end.isoformat(),
    }
    return total_earned, summary


def _daily_wage_earnings(
    employee_id: int,
    daily_rate: Decimal,
    from_date: date | None,
    to_date: date | None,
    Attendance,   # model class passed in
) -> tuple[Decimal, dict]:
    """
    Earnings = daily_rate × number_of_present_attendance_days.

    Attendance.status accepted values (case-insensitive):
        "present", "Present", "PRESENT", "P"
    """
    q = Attendance.query.filter(
        Attendance.user_id == employee_id,
        Attendance.status.in_(["present", "Present", "PRESENT", "P"]),
    )
    if from_date:
        q = q.filter(Attendance.date >= from_date)
    if to_date:
        q = q.filter(Attendance.date <= to_date)

    days_present = q.count()
    total_earned = daily_rate * Decimal(str(days_present))

    summary = {
        "days_present":  days_present,
        "daily_rate":    float(daily_rate),
    }
    return total_earned, summary


def _per_task_earnings(
    employee_id: int,
    per_task_rate: Decimal,
    from_date: date | None,
    to_date: date | None,
    Task,   # model class passed in
) -> tuple[Decimal, dict]:
    """
    Earnings = per_task_rate × number_of_completed_tasks.

    Task.status accepted values: "completed", "Completed", "COMPLETED", "done"
    Task date field tried in order: completed_at, updated_at, created_at
    """
    # Build base query — filter by assigned_to or user_id depending on your schema
    # Adjust 'assigned_to' to whatever field links task → employee in your Task model
    q = Task.query.filter(
        Task.assigned_to == employee_id,
        Task.status.in_(["completed", "Completed", "COMPLETED", "done"]),
    )

    if from_date or to_date:
        # Use whatever date column exists: completed_at preferred, else created_at
        date_col = _task_date_col(Task)
        if date_col is not None:
            if from_date:
                q = q.filter(date_col >= from_date)
            if to_date:
                q = q.filter(date_col <= to_date)

    tasks_completed = q.count()
    total_earned    = per_task_rate * Decimal(str(tasks_completed))

    summary = {
        "tasks_completed": tasks_completed,
        "per_task_rate":   float(per_task_rate),
    }
    return total_earned, summary


def _task_date_col(Task):
    """Return the best date column available on the Task model."""
    for col_name in ("completed_at", "updated_at", "created_at"):
        col = getattr(Task, col_name, None)
        if col is not None:
            return col
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Balance ledger
# ─────────────────────────────────────────────────────────────────────────────

def get_balance_summary(
    employee_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Returns the complete balance ledger for an employee.

    {
        "employee_id":    int,
        "total_earned":   float,
        "total_paid":     float,
        "remaining":      float,
        "wage_type":      str,
        "wage_amount":    float,
        "work_summary":   { ... },
    }
    """
    earnings    = calculate_earnings(employee_id, from_date, to_date)
    total_paid  = float(_total_paid(employee_id))
    remaining   = earnings["total_earned"] - total_paid

    return {
        "employee_id":  employee_id,
        "total_earned": earnings["total_earned"],
        "total_paid":   total_paid,
        "remaining":    remaining,
        "wage_type":    earnings["wage_type"],
        "wage_amount":  earnings["wage_amount"],
        "work_summary": earnings["work_summary"],
        "from_date":    earnings["from_date"],
        "to_date":      earnings["to_date"],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Utility
# ─────────────────────────────────────────────────────────────────────────────

def _count_months(start: date, end: date) -> int:
    """Number of calendar months between start and end (inclusive)."""
    if end < start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month) + 1
