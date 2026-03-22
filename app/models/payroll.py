from datetime import datetime
from app.extensions import db


class SalaryStructure(db.Model):
    """Employee salary structure - basic + components."""
    __tablename__ = "salary_structures"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # Basic
    basic_salary = db.Column(db.Float, nullable=False, default=0)
    hra = db.Column(db.Float, default=0)  # House Rent Allowance
    da = db.Column(db.Float, default=0)   # Dearness Allowance
    conveyance = db.Column(db.Float, default=0)
    medical_allowance = db.Column(db.Float, default=0)
    special_allowance = db.Column(db.Float, default=0)
    other_allowance = db.Column(db.Float, default=0)

    # Deductions
    pf_employee = db.Column(db.Float, default=0)     # Employee PF contribution
    pf_employer = db.Column(db.Float, default=0)     # Employer PF contribution
    esi_employee = db.Column(db.Float, default=0)    # Employee ESI
    esi_employer = db.Column(db.Float, default=0)    # Employer ESI
    professional_tax = db.Column(db.Float, default=0)
    tds = db.Column(db.Float, default=0)             # Tax Deducted at Source
    other_deduction = db.Column(db.Float, default=0)

    # Calculated
    gross_salary = db.Column(db.Float, default=0)
    total_deductions = db.Column(db.Float, default=0)
    net_salary = db.Column(db.Float, default=0)
    ctc = db.Column(db.Float, default=0)  # Cost to Company

    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date, nullable=True)  # NULL = current
    is_active = db.Column(db.Boolean, default=True)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id], backref="salary_structures")
    creator = db.relationship("User", foreign_keys=[created_by])

    def calculate(self):
        """Recalculate gross, deductions, net, and CTC."""
        self.gross_salary = round(
            self.basic_salary + self.hra + self.da + self.conveyance +
            self.medical_allowance + self.special_allowance + self.other_allowance, 2
        )
        self.total_deductions = round(
            self.pf_employee + self.esi_employee + self.professional_tax +
            self.tds + self.other_deduction, 2
        )
        self.net_salary = round(self.gross_salary - self.total_deductions, 2)
        self.ctc = round(self.gross_salary + self.pf_employer + self.esi_employer, 2)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_id": self.user.employee_id if self.user else None,
            "employee_name": f"{self.user.first_name} {self.user.last_name}" if self.user else None,
            "basic_salary": self.basic_salary,
            "hra": self.hra,
            "da": self.da,
            "conveyance": self.conveyance,
            "medical_allowance": self.medical_allowance,
            "special_allowance": self.special_allowance,
            "other_allowance": self.other_allowance,
            "gross_salary": self.gross_salary,
            "pf_employee": self.pf_employee,
            "pf_employer": self.pf_employer,
            "esi_employee": self.esi_employee,
            "esi_employer": self.esi_employer,
            "professional_tax": self.professional_tax,
            "tds": self.tds,
            "other_deduction": self.other_deduction,
            "total_deductions": self.total_deductions,
            "net_salary": self.net_salary,
            "ctc": self.ctc,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class DailyWage(db.Model):
    """Daily/weekly wage tracking for piece-rate or daily workers."""
    __tablename__ = "daily_wages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)

    # Work details
    hours_worked = db.Column(db.Float, default=0)
    per_hour_rate = db.Column(db.Float, default=0)
    per_day_rate = db.Column(db.Float, default=0)  # Fixed daily rate (if not hourly)
    pieces_completed = db.Column(db.Integer, default=0)  # For piece-rate workers
    per_piece_rate = db.Column(db.Float, default=0)

    # Earnings
    base_pay = db.Column(db.Float, default=0)
    overtime_hours = db.Column(db.Float, default=0)
    overtime_rate = db.Column(db.Float, default=0)  # e.g., 1.5x or 2x
    overtime_pay = db.Column(db.Float, default=0)
    bonus = db.Column(db.Float, default=0)
    deduction = db.Column(db.Float, default=0)
    total_pay = db.Column(db.Float, default=0)

    # Payment
    payment_status = db.Column(
        db.Enum("pending", "paid", name="daily_payment_status_enum"),
        default="pending",
        nullable=False,
        index=True,
    )
    payment_mode = db.Column(db.String(50), nullable=True)  # cash, bank_transfer, upi
    payment_ref = db.Column(db.String(100), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    paid_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    notes = db.Column(db.String(500), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "date", name="uq_daily_wage_user_date"),
    )

    user = db.relationship("User", foreign_keys=[user_id], backref="daily_wages")
    creator = db.relationship("User", foreign_keys=[created_by])
    payer = db.relationship("User", foreign_keys=[paid_by])

    def calculate(self):
            """Auto-calculate total pay."""
            if self.per_day_rate and self.per_day_rate > 0:
                self.base_pay = self.per_day_rate
            elif self.per_hour_rate and self.per_hour_rate > 0 and self.hours_worked and self.hours_worked > 0:
                self.base_pay = round(self.per_hour_rate * self.hours_worked, 2)
            elif self.per_piece_rate and self.per_piece_rate > 0 and self.pieces_completed and self.pieces_completed > 0:
                self.base_pay = round(self.per_piece_rate * self.pieces_completed, 2)

            if self.overtime_hours and self.overtime_hours > 0 and self.overtime_rate and self.overtime_rate > 0:
                hourly = self.per_hour_rate if (self.per_hour_rate and self.per_hour_rate > 0) else (self.per_day_rate / 8 if (self.per_day_rate and self.per_day_rate > 0) else 0)
                self.overtime_pay = round(self.overtime_hours * hourly * self.overtime_rate, 2)
            else:
                self.overtime_pay = 0

            self.total_pay = round((self.base_pay or 0) + (self.overtime_pay or 0) + (self.bonus or 0) - (self.deduction or 0), 2)
            
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_id": self.user.employee_id if self.user else None,
            "employee_name": f"{self.user.first_name} {self.user.last_name}" if self.user else None,
            "date": self.date.isoformat() if self.date else None,
            "hours_worked": self.hours_worked,
            "per_hour_rate": self.per_hour_rate,
            "per_day_rate": self.per_day_rate,
            "pieces_completed": self.pieces_completed,
            "per_piece_rate": self.per_piece_rate,
            "base_pay": self.base_pay,
            "overtime_hours": self.overtime_hours,
            "overtime_rate": self.overtime_rate,
            "overtime_pay": self.overtime_pay,
            "bonus": self.bonus,
            "deduction": self.deduction,
            "total_pay": self.total_pay,
            "payment_status": self.payment_status,
            "payment_mode": self.payment_mode,
            "payment_ref": self.payment_ref,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
class Payslip(db.Model):
    """Monthly payslip for each employee."""
    __tablename__ = "payslips"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    salary_structure_id = db.Column(db.Integer, db.ForeignKey("salary_structures.id"), nullable=False)

    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)

    # From salary structure (snapshot at time of generation)
    basic_salary = db.Column(db.Float, default=0)
    hra = db.Column(db.Float, default=0)
    da = db.Column(db.Float, default=0)
    conveyance = db.Column(db.Float, default=0)
    medical_allowance = db.Column(db.Float, default=0)
    special_allowance = db.Column(db.Float, default=0)
    other_allowance = db.Column(db.Float, default=0)

    # Deductions
    pf_employee = db.Column(db.Float, default=0)
    esi_employee = db.Column(db.Float, default=0)
    professional_tax = db.Column(db.Float, default=0)
    tds = db.Column(db.Float, default=0)
    other_deduction = db.Column(db.Float, default=0)

    # Adjustments
    overtime_pay = db.Column(db.Float, default=0)
    bonus = db.Column(db.Float, default=0)
    leave_deduction = db.Column(db.Float, default=0)  # Unpaid leave deduction
    late_deduction = db.Column(db.Float, default=0)

    # Attendance summary for the month
    working_days = db.Column(db.Integer, default=0)
    present_days = db.Column(db.Float, default=0)
    leave_days = db.Column(db.Float, default=0)
    absent_days = db.Column(db.Float, default=0)
    overtime_hours = db.Column(db.Float, default=0)

    # Totals
    gross_earnings = db.Column(db.Float, default=0)
    total_deductions = db.Column(db.Float, default=0)
    net_pay = db.Column(db.Float, default=0)

    # Payment
    payment_status = db.Column(
        db.Enum("pending", "processed", "paid", "failed", name="payment_status_enum"),
        default="pending",
        nullable=False,
        index=True,
    )
    payment_date = db.Column(db.Date, nullable=True)
    payment_mode = db.Column(db.String(50), nullable=True)  # bank_transfer, cash, cheque
    transaction_ref = db.Column(db.String(100), nullable=True)
    payment_notes = db.Column(db.Text, nullable=True)

    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "month", "year", name="uq_user_month_year"),
    )

    user = db.relationship("User", foreign_keys=[user_id], backref="payslips")
    salary_structure = db.relationship("SalaryStructure", backref="payslips")
    generator = db.relationship("User", foreign_keys=[generated_by])

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_id": self.user.employee_id if self.user else None,
            "employee_name": f"{self.user.first_name} {self.user.last_name}" if self.user else None,
            "month": self.month,
            "year": self.year,
            "month_name": ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][self.month],
            "basic_salary": self.basic_salary,
            "hra": self.hra, "da": self.da, "conveyance": self.conveyance,
            "medical_allowance": self.medical_allowance,
            "special_allowance": self.special_allowance,
            "other_allowance": self.other_allowance,
            "overtime_pay": self.overtime_pay,
            "bonus": self.bonus,
            "gross_earnings": self.gross_earnings,
            "pf_employee": self.pf_employee, "esi_employee": self.esi_employee,
            "professional_tax": self.professional_tax, "tds": self.tds,
            "other_deduction": self.other_deduction,
            "leave_deduction": self.leave_deduction,
            "late_deduction": self.late_deduction,
            "total_deductions": self.total_deductions,
            "net_pay": self.net_pay,
            "working_days": self.working_days,
            "present_days": self.present_days,
            "leave_days": self.leave_days,
            "absent_days": self.absent_days,
            "overtime_hours": self.overtime_hours,
            "payment_status": self.payment_status,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "payment_mode": self.payment_mode,
            "transaction_ref": self.transaction_ref,
            "payment_notes": self.payment_notes,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }