from datetime import datetime
from app.extensions import db


class Task(db.Model):
    """Work assignment / task for employees."""
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Assignment
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Status
    status = db.Column(
        db.Enum("pending", "in_progress", "completed", "cancelled", "on_hold", name="task_status_enum"),
        default="pending",
        nullable=False,
        index=True,
    )
    priority = db.Column(
        db.Enum("low", "medium", "high", "urgent", name="task_priority_enum"),
        default="medium",
        nullable=False,
    )

    # Dates
    due_date = db.Column(db.Date, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Work details (jewellery specific)
    category = db.Column(db.String(100), nullable=True)  # e.g., "Gold Ring", "Diamond Setting", "Polishing"
    estimated_hours = db.Column(db.Float, nullable=True)
    actual_hours = db.Column(db.Float, nullable=True)
    quantity = db.Column(db.Integer, default=1)
    weight_grams = db.Column(db.Float, nullable=True)  # metal weight

    # Notes
    admin_notes = db.Column(db.Text, nullable=True)
    employee_notes = db.Column(db.Text, nullable=True)
    completion_notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assignee = db.relationship("User", foreign_keys=[assigned_to], backref="assigned_tasks")
    assigner = db.relationship("User", foreign_keys=[assigned_by], backref="created_tasks")
    comments = db.relationship("TaskComment", backref="task", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self, include_comments=False):
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "assigned_to": self.assigned_to,
            "assigned_by": self.assigned_by,
            "assignee_name": f"{self.assignee.first_name} {self.assignee.last_name}" if self.assignee else None,
            "assigner_name": f"{self.assigner.first_name} {self.assigner.last_name}" if self.assigner else None,
            "assignee_employee_id": self.assignee.employee_id if self.assignee else None,
            "status": self.status,
            "priority": self.priority,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "category": self.category,
            "estimated_hours": self.estimated_hours,
            "actual_hours": self.actual_hours,
            "quantity": self.quantity,
            "weight_grams": self.weight_grams,
            "admin_notes": self.admin_notes,
            "employee_notes": self.employee_notes,
            "completion_notes": self.completion_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_comments:
            data["comments"] = [c.to_dict() for c in self.comments.order_by(TaskComment.created_at.asc()).all()]
        return data


class TaskComment(db.Model):
    """Comments/notes on a task - conversation between admin and employee."""
    __tablename__ = "task_comments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="task_comments")

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "user_name": f"{self.user.first_name} {self.user.last_name}" if self.user else None,
            "user_role": self.user.role if self.user else None,
            "comment": self.comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }