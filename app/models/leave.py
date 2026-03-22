from datetime import datetime, date
from app.extensions import db


class LeaveType(db.Model):
    """Configurable leave types with annual quotas."""
    __tablename__ = "leave_types"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # casual, sick, earned, unpaid
    code = db.Column(db.String(10), unique=True, nullable=False)  # CL, SL, EL, UL
    annual_quota = db.Column(db.Integer, default=0)  # 0 = unlimited (e.g., unpaid)
    is_paid = db.Column(db.Boolean, default=True)
    is_carry_forward = db.Column(db.Boolean, default=False)
    max_carry_forward = db.Column(db.Integer, default=0)
    requires_approval = db.Column(db.Boolean, default=True)
    min_days_advance = db.Column(db.Integer, default=0)  # How many days before to apply
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "annual_quota": self.annual_quota,
            "is_paid": self.is_paid,
            "is_carry_forward": self.is_carry_forward,
            "max_carry_forward": self.max_carry_forward,
            "requires_approval": self.requires_approval,
            "min_days_advance": self.min_days_advance,
            "description": self.description,
            "is_active": self.is_active,
        }


class LeaveBalance(db.Model):
    """Per-user, per-year leave balance tracking."""
    __tablename__ = "leave_balances"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_quota = db.Column(db.Integer, default=0)
    used = db.Column(db.Float, default=0)  # Float for half-days
    carry_forward = db.Column(db.Integer, default=0)

    user = db.relationship("User", backref="leave_balances")
    leave_type = db.relationship("LeaveType", backref="balances")

    __table_args__ = (
        db.UniqueConstraint("user_id", "leave_type_id", "year", name="uq_user_leavetype_year"),
    )

    @property
    def available(self):
        return self.total_quota + self.carry_forward - self.used

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "leave_type_id": self.leave_type_id,
            "leave_type_name": self.leave_type.name if self.leave_type else None,
            "leave_type_code": self.leave_type.code if self.leave_type else None,
            "year": self.year,
            "total_quota": self.total_quota,
            "carry_forward": self.carry_forward,
            "used": self.used,
            "available": self.available,
        }


class LeaveRequest(db.Model):
    """Employee leave applications."""
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)

    from_date = db.Column(db.Date, nullable=False)
    to_date = db.Column(db.Date, nullable=False)
    total_days = db.Column(db.Float, nullable=False)  # Float for half-days
    is_half_day = db.Column(db.Boolean, default=False)
    half_day_period = db.Column(db.Enum("first_half", "second_half", name="half_day_enum"), nullable=True)

    reason = db.Column(db.Text, nullable=False)

    status = db.Column(
        db.Enum("pending", "approved", "rejected", "cancelled", name="leave_status_enum"),
        default="pending",
        nullable=False,
        index=True,
    )

    # Approval
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_comment = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id], backref="leave_requests")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    leave_type = db.relationship("LeaveType", backref="requests")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_id": self.user.employee_id if self.user else None,
            "employee_name": f"{self.user.first_name} {self.user.last_name}" if self.user else None,
            "leave_type_id": self.leave_type_id,
            "leave_type_name": self.leave_type.name if self.leave_type else None,
            "leave_type_code": self.leave_type.code if self.leave_type else None,
            "from_date": self.from_date.isoformat() if self.from_date else None,
            "to_date": self.to_date.isoformat() if self.to_date else None,
            "total_days": self.total_days,
            "is_half_day": self.is_half_day,
            "half_day_period": self.half_day_period,
            "reason": self.reason,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewer_name": f"{self.reviewer.first_name} {self.reviewer.last_name}" if self.reviewer else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_comment": self.review_comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Holiday(db.Model):
    """Company holidays calendar."""
    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False, unique=True)
    is_optional = db.Column(db.Boolean, default=False)
    year = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "date": self.date.isoformat() if self.date else None,
            "is_optional": self.is_optional,
            "year": self.year,
        }