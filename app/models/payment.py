"""
JewelCraft HRM — Payment System Models
File: app/models/payment.py

Add this file to your existing app/models/ directory.
Then import these models in app/models/__init__.py
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum
from app.extensions import db  # use your existing db instance


# ─────────────────────────────────────────────────────────────────────────────
#  Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class WageType(str, PyEnum):
    """How this employee's earnings are calculated."""
    MONTHLY_SALARY  = "monthly_salary"   # fixed monthly amount
    DAILY_WAGE      = "daily_wage"       # per attendance day worked
    PER_TASK        = "per_task"         # per completed task


class PaymentMethod(str, PyEnum):
    CASH        = "cash"
    BANK        = "bank"
    UPI         = "upi"


class PaymentStatus(str, PyEnum):
    COMPLETED   = "completed"
    REVERSED    = "reversed"   # for corrections / refunds


# ─────────────────────────────────────────────────────────────────────────────
#  EmployeePaymentConfig
#  One row per employee.  Admin can create/update via API.
# ─────────────────────────────────────────────────────────────────────────────

class EmployeePaymentConfig(db.Model):
    """
    Stores *how* and *how much* an employee should be paid.

    wage_type     → which earnings formula to use
    wage_amount   → meaning depends on wage_type:
                      MONTHLY_SALARY  → monthly gross (₹)
                      DAILY_WAGE      → amount per working day (₹)
                      PER_TASK        → amount per completed task (₹)
    effective_from → configs can be versioned; only the latest active one is used
    """

    __tablename__ = "employee_payment_configs"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    wage_type       = db.Column(
        db.Enum(WageType, name="wage_type_enum"),
        nullable=False,
        default=WageType.MONTHLY_SALARY,
    )
    wage_amount     = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # optional: task-rate override per task category can be added later
    effective_from  = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    is_active       = db.Column(db.Boolean, nullable=False, default=True)

    notes           = db.Column(db.Text, nullable=True)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = db.relationship("User", backref=db.backref("payment_config", uselist=False))

    def to_dict(self):
        return {
            "id":             self.id,
            "user_id":        self.user_id,
            "wage_type":      self.wage_type.value,
            "wage_amount":    float(self.wage_amount),
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "is_active":      self.is_active,
            "notes":          self.notes,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<PaymentConfig user_id={self.user_id} type={self.wage_type}>"


# ─────────────────────────────────────────────────────────────────────────────
#  PaymentTransaction
#  Every cash-out to an employee is recorded here.
# ─────────────────────────────────────────────────────────────────────────────

class PaymentTransaction(db.Model):
    """
    Immutable ledger of payments made to an employee.
    Each row reduces the employee's remaining_balance.
    """

    __tablename__ = "payment_transactions"

    id              = db.Column(db.Integer, primary_key=True)
    employee_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    paid_by         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    amount          = db.Column(db.Numeric(12, 2), nullable=False)
    payment_date    = db.Column(db.Date, nullable=False)
    payment_method  = db.Column(
        db.Enum(PaymentMethod, name="payment_method_enum"),
        nullable=False,
        default=PaymentMethod.CASH,
    )
    reference_note  = db.Column(db.String(500), nullable=True)

    status          = db.Column(
        db.Enum(PaymentStatus, name="payment_status_enum"),
        nullable=False,
        default=PaymentStatus.COMPLETED,
    )
    reversal_of     = db.Column(db.Integer, db.ForeignKey("payment_transactions.id"), nullable=True)
    reversal_reason = db.Column(db.String(500), nullable=True)

    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    employee        = db.relationship("User", foreign_keys=[employee_id],
                                      backref=db.backref("payments_received", lazy="dynamic"))
    admin           = db.relationship("User", foreign_keys=[paid_by])

    def to_dict(self):
        return {
            "id":             self.id,
            "employee_id":    self.employee_id,
            "paid_by":        self.paid_by,
            "amount":         float(self.amount),
            "payment_date":   self.payment_date.isoformat() if self.payment_date else None,
            "payment_method": self.payment_method.value,
            "reference_note": self.reference_note,
            "status":         self.status.value,
            "reversal_of":    self.reversal_of,
            "reversal_reason":self.reversal_reason,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            # populated in routes via join
            "employee_name":  None,
            "paid_by_name":   None,
        }

    def __repr__(self):
        return f"<Payment #{self.id} emp={self.employee_id} ₹{self.amount}>"
