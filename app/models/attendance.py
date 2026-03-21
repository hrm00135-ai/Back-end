from datetime import datetime, date, time, timedelta
from app.extensions import db


class AttendanceConfig(db.Model):
    """Configurable attendance settings per location/department."""
    __tablename__ = "attendance_config"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # e.g., "Mumbai Workshop"

    shift_start = db.Column(db.Time, default=time(9, 0))    # 09:00 AM
    shift_end = db.Column(db.Time, default=time(18, 0))      # 06:00 PM
    late_threshold_minutes = db.Column(db.Integer, default=15)  # Grace period
    half_day_threshold_hours = db.Column(db.Float, default=4.0)
    full_day_threshold_hours = db.Column(db.Float, default=8.0)
    overtime_after_hours = db.Column(db.Float, default=9.0)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "shift_start": self.shift_start.strftime("%H:%M") if self.shift_start else None,
            "shift_end": self.shift_end.strftime("%H:%M") if self.shift_end else None,
            "late_threshold_minutes": self.late_threshold_minutes,
            "half_day_threshold_hours": self.half_day_threshold_hours,
            "full_day_threshold_hours": self.full_day_threshold_hours,
            "overtime_after_hours": self.overtime_after_hours,
            "is_active": self.is_active,
        }


class Attendance(db.Model):
    """Daily attendance record for each employee."""
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)

    # Check-in
    check_in_time = db.Column(db.DateTime, nullable=True)
    check_in_lat = db.Column(db.Float, nullable=True)
    check_in_lng = db.Column(db.Float, nullable=True)
    check_in_address = db.Column(db.String(500), nullable=True)

    # Check-out
    check_out_time = db.Column(db.DateTime, nullable=True)
    check_out_lat = db.Column(db.Float, nullable=True)
    check_out_lng = db.Column(db.Float, nullable=True)
    check_out_address = db.Column(db.String(500), nullable=True)

    # Calculated fields
    total_hours = db.Column(db.Float, nullable=True)
    overtime_hours = db.Column(db.Float, default=0)
    is_late = db.Column(db.Boolean, default=False)
    late_minutes = db.Column(db.Integer, default=0)

    # Status
    status = db.Column(
        db.Enum("present", "absent", "half_day", "on_leave", "holiday", "weekend",
                name="attendance_status_enum"),
        default="present",
        nullable=False,
    )

    # Admin override
    is_manually_edited = db.Column(db.Boolean, default=False)
    edited_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    edit_reason = db.Column(db.String(500), nullable=True)

    notes = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id], backref="attendance_records")
    editor = db.relationship("User", foreign_keys=[edited_by])

    # Unique constraint: one record per user per day
    __table_args__ = (
        db.UniqueConstraint("user_id", "date", name="uq_user_date"),
    )

    def calculate_hours(self, config=None):
        """Calculate total hours, overtime, and late status."""
        if not self.check_in_time or not self.check_out_time:
            return

        delta = self.check_out_time - self.check_in_time
        self.total_hours = round(delta.total_seconds() / 3600, 2)

        if config:
            # Late check
            shift_start_dt = datetime.combine(self.date, config.shift_start)
            grace_dt = shift_start_dt + timedelta(minutes=config.late_threshold_minutes)

            if self.check_in_time > grace_dt:
                self.is_late = True
                self.late_minutes = int((self.check_in_time - shift_start_dt).total_seconds() / 60)
            else:
                self.is_late = False
                self.late_minutes = 0

            # Overtime
            if self.total_hours > config.overtime_after_hours:
                self.overtime_hours = round(self.total_hours - config.overtime_after_hours, 2)
            else:
                self.overtime_hours = 0

            # Status based on hours
            if self.total_hours >= config.full_day_threshold_hours:
                self.status = "present"
            elif self.total_hours >= config.half_day_threshold_hours:
                self.status = "half_day"
            else:
                self.status = "half_day"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_id": self.user.employee_id if self.user else None,
            "employee_name": f"{self.user.first_name} {self.user.last_name}" if self.user else None,
            "date": self.date.isoformat() if self.date else None,
            "check_in_time": self.check_in_time.isoformat() if self.check_in_time else None,
            "check_in_lat": self.check_in_lat,
            "check_in_lng": self.check_in_lng,
            "check_in_address": self.check_in_address,
            "check_out_time": self.check_out_time.isoformat() if self.check_out_time else None,
            "check_out_lat": self.check_out_lat,
            "check_out_lng": self.check_out_lng,
            "check_out_address": self.check_out_address,
            "total_hours": self.total_hours,
            "overtime_hours": self.overtime_hours,
            "is_late": self.is_late,
            "late_minutes": self.late_minutes,
            "status": self.status,
            "is_manually_edited": self.is_manually_edited,
            "edited_by": self.edited_by,
            "edit_reason": self.edit_reason,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }