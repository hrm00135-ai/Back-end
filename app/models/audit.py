from datetime import datetime
from app.extensions import db
import hashlib
import json


class SystemLog(db.Model):
    """Tamper-proof system log - hidden from all roles, backend-only access.
    Each entry is hash-chained to the previous entry for integrity verification."""
    __tablename__ = "system_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Who
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user_email = db.Column(db.String(255), nullable=True)
    user_role = db.Column(db.String(50), nullable=True)
    employee_id = db.Column(db.String(20), nullable=True)

    # What
    action = db.Column(db.String(100), nullable=False, index=True)
    resource = db.Column(db.String(100), nullable=True)  # e.g., "user", "task", "attendance"
    resource_id = db.Column(db.Integer, nullable=True)
    
    # Before/After values for changes
    before_value = db.Column(db.Text, nullable=True)  # JSON snapshot before change
    after_value = db.Column(db.Text, nullable=True)   # JSON snapshot after change
    details = db.Column(db.Text, nullable=True)        # Additional context

    # Where
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    endpoint = db.Column(db.String(255), nullable=True)
    method = db.Column(db.String(10), nullable=True)  # GET, POST, PUT, DELETE

    # Integrity
    previous_hash = db.Column(db.String(64), nullable=True)  # SHA-256 of previous entry
    entry_hash = db.Column(db.String(64), nullable=False)     # SHA-256 of this entry

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", foreign_keys=[user_id])

    def compute_hash(self):
            """Compute SHA-256 hash of this entry for chain integrity."""
            ts = self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else ""
            data = f"{self.user_id}|{self.action}|{self.resource}|{self.resource_id}|{self.details}|{self.ip_address}|{ts}|{self.previous_hash}"
            return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "user_role": self.user_role,
            "employee_id": self.employee_id,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "endpoint": self.endpoint,
            "method": self.method,
            "entry_hash": self.entry_hash,
            "previous_hash": self.previous_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }