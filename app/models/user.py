from datetime import datetime
from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum("super_admin", "admin", "employee", name="user_role"),
        nullable=False,
        index=True,
    )
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    alt_phone = db.Column(db.String(20), nullable=True)
    photo_url = db.Column(db.String(500), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    designation = db.Column(db.String(100), nullable=True)
    date_of_joining = db.Column(db.Date, nullable=False)
    date_of_leaving = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_locked = db.Column(db.Boolean, default=False)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_at = db.Column(db.DateTime, nullable=True)
    location_of_work = db.Column(db.String(255), nullable=True)
    registered_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    registrar = db.relationship(
        "User", remote_side=[id], backref="registered_users", foreign_keys=[registered_by]
    )

    def to_dict(self, include_sensitive=False):
        data = {
            "id": self.id,
            "employee_id": self.employee_id,
            "email": self.email,
            "role": self.role,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "alt_phone": self.alt_phone,
            "photo_url": self.photo_url,
            "department": self.department,
            "designation": self.designation,
            "date_of_joining": self.date_of_joining.isoformat() if self.date_of_joining else None,
            "date_of_leaving": self.date_of_leaving.isoformat() if self.date_of_leaving else None,
            "is_active": self.is_active,
            "is_locked": self.is_locked,
            "location_of_work": self.location_of_work,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_sensitive:
            data["failed_login_attempts"] = self.failed_login_attempts
            data["locked_at"] = self.locked_at.isoformat() if self.locked_at else None
            data["registered_by"] = self.registered_by
        return data

    def __repr__(self):
        return f"<User {self.employee_id} - {self.first_name} {self.last_name} ({self.role})>"
