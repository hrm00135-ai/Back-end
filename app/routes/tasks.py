from datetime import datetime, date
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.user import User
from app.models.task import Task, TaskComment
from app.utils.helpers import log_audit, success_response, error_response

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


# ============================================================
# CREATE TASK (Admin/Super Admin assigns to employee)
# ============================================================
@tasks_bp.route("/", methods=["POST"])
@jwt_required()
def create_task():
    """
    Admin/Super Admin creates a task and assigns it to an employee.
    Body: { "title", "assigned_to", "description", "priority", "due_date", "category", ... }
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can create tasks", 403)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    title = data.get("title", "").strip()
    assigned_to = data.get("assigned_to")

    if not title:
        return error_response("Title is required", 400)
    if not assigned_to:
        return error_response("assigned_to (user ID) is required", 400)

    # Validate assignee exists and is an employee
    assignee = User.query.get(int(assigned_to))
    if not assignee:
        return error_response("Assigned user not found", 404)
    if not assignee.is_active:
        return error_response("Cannot assign task to inactive user", 400)

    # Parse due_date
    due_date = None
    if data.get("due_date"):
        try:
            due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid due_date format. Use YYYY-MM-DD", 400)

    task = Task(
        title=title,
        description=data.get("description", "").strip() or None,
        assigned_to=int(assigned_to),
        assigned_by=current_user_id,
        priority=data.get("priority", "medium"),
        due_date=due_date,
        category=data.get("category", "").strip() or None,
        estimated_hours=data.get("estimated_hours"),
        quantity=data.get("quantity", 1),
        weight_grams=data.get("weight_grams"),
        admin_notes=data.get("admin_notes", "").strip() or None,
    )

    db.session.add(task)
    db.session.commit()

    log_audit(current_user_id, "CREATE_TASK", target_user_id=int(assigned_to),
              details={"task_id": task.id, "title": title})

    return success_response(data=task.to_dict(), message="Task created successfully", status_code=201)


# ============================================================
# LIST TASKS
# ============================================================
@tasks_bp.route("/", methods=["GET"])
@jwt_required()
def list_tasks():
    """
    List tasks with filters.
    Employee sees own tasks. Admin sees tasks they assigned + employee tasks. Super Admin sees all.
    Query params: status, priority, assigned_to, category, page, per_page
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    query = Task.query

    # Role-based filtering
    if current_user.role == "employee":
        query = query.filter_by(assigned_to=current_user_id)
    elif current_user.role == "admin":
        # Admin sees tasks they created or assigned to their employees
        query = query.filter(
            db.or_(
                Task.assigned_by == current_user_id,
                Task.assigned_to == current_user_id,
            )
        )
    # Super Admin sees all

    # Filters
    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)

    priority = request.args.get("priority")
    if priority:
        query = query.filter_by(priority=priority)

    assigned_to = request.args.get("assigned_to")
    if assigned_to:
        query = query.filter_by(assigned_to=int(assigned_to))

    category = request.args.get("category")
    if category:
        query = query.filter_by(category=category)

    # Date range filter
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    if from_date:
        try:
            query = query.filter(Task.created_at >= datetime.strptime(from_date, "%Y-%m-%d"))
        except ValueError:
            pass
    if to_date:
        try:
            query = query.filter(Task.created_at <= datetime.strptime(to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = query.order_by(Task.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return success_response(data={
        "tasks": [t.to_dict() for t in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
        "per_page": pagination.per_page,
    })


# ============================================================
# GET TASK BY ID
# ============================================================
@tasks_bp.route("/<int:task_id>", methods=["GET"])
@jwt_required()
def get_task(task_id):
    """Get task details with comments."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    task = Task.query.get(task_id)
    if not task:
        return error_response("Task not found", 404)

    # Access control
    if current_user.role == "employee" and task.assigned_to != current_user_id:
        return error_response("Insufficient permissions", 403)
    if current_user.role == "admin" and task.assigned_by != current_user_id and task.assigned_to != current_user_id:
        return error_response("Insufficient permissions", 403)

    return success_response(data=task.to_dict(include_comments=True))


# ============================================================
# UPDATE TASK (Admin/Super Admin)
# ============================================================
@tasks_bp.route("/<int:task_id>", methods=["PUT"])
@jwt_required()
def update_task(task_id):
    """
    Update task details. Admin/Super Admin can update anything.
    Employee can only update: status, employee_notes, actual_hours, completion_notes
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    task = Task.query.get(task_id)
    if not task:
        return error_response("Task not found", 404)

    # Access control
    if current_user.role == "employee" and task.assigned_to != current_user_id:
        return error_response("Insufficient permissions", 403)
    if current_user.role == "admin" and task.assigned_by != current_user_id and task.assigned_to != current_user_id:
        return error_response("Insufficient permissions", 403)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    # Admin/Super Admin fields
    if current_user.role in ("admin", "super_admin"):
        admin_fields = ["title", "description", "priority", "category",
                        "estimated_hours", "quantity", "weight_grams", "admin_notes"]
        for field in admin_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str):
                    value = value.strip() or None
                setattr(task, field, value)

        if "assigned_to" in data:
            new_assignee = User.query.get(int(data["assigned_to"]))
            if not new_assignee or not new_assignee.is_active:
                return error_response("Invalid assignee", 400)
            task.assigned_to = int(data["assigned_to"])

        if "due_date" in data:
            if data["due_date"]:
                try:
                    task.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
                except ValueError:
                    return error_response("Invalid due_date format", 400)
            else:
                task.due_date = None

    # Fields both employee and admin can update
    if "status" in data:
        old_status = task.status
        new_status = data["status"]

        valid_statuses = ["pending", "in_progress", "completed", "cancelled", "on_hold"]
        if new_status not in valid_statuses:
            return error_response(f"Invalid status. Must be one of: {', '.join(valid_statuses)}", 400)

        # Employee can only move: pending->in_progress, in_progress->completed
        if current_user.role == "employee":
            allowed_transitions = {
                "pending": ["in_progress"],
                "in_progress": ["completed", "on_hold"],
                "on_hold": ["in_progress"],
            }
            if new_status not in allowed_transitions.get(old_status, []):
                return error_response(f"Cannot change status from {old_status} to {new_status}", 400)

        task.status = new_status

        # Auto-set timestamps
        if new_status == "in_progress" and not task.started_at:
            task.started_at = datetime.utcnow()
        elif new_status == "completed":
            task.completed_at = datetime.utcnow()

    if "employee_notes" in data:
        task.employee_notes = data["employee_notes"].strip() or None

    if "actual_hours" in data:
        task.actual_hours = data["actual_hours"]

    if "completion_notes" in data:
        task.completion_notes = data["completion_notes"].strip() or None

    db.session.commit()

    log_audit(current_user_id, "UPDATE_TASK", details={"task_id": task_id, "changes": list(data.keys())})

    return success_response(data=task.to_dict(), message="Task updated successfully")


# ============================================================
# DELETE TASK (Admin/Super Admin only)
# ============================================================
@tasks_bp.route("/<int:task_id>", methods=["DELETE"])
@jwt_required()
def delete_task(task_id):
    """Delete a task. Only Admin/Super Admin."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can delete tasks", 403)

    task = Task.query.get(task_id)
    if not task:
        return error_response("Task not found", 404)

    db.session.delete(task)
    db.session.commit()

    log_audit(current_user_id, "DELETE_TASK", details={"task_id": task_id, "title": task.title})

    return success_response(message="Task deleted successfully")


# ============================================================
# ADD COMMENT TO TASK
# ============================================================
@tasks_bp.route("/<int:task_id>/comments", methods=["POST"])
@jwt_required()
def add_comment(task_id):
    """Add a comment to a task. Both admin and employee can comment."""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    task = Task.query.get(task_id)
    if not task:
        return error_response("Task not found", 404)

    # Access control
    if current_user.role == "employee" and task.assigned_to != current_user_id:
        return error_response("Insufficient permissions", 403)

    data = request.get_json()
    if not data or not data.get("comment", "").strip():
        return error_response("Comment is required", 400)

    comment = TaskComment(
        task_id=task_id,
        user_id=current_user_id,
        comment=data["comment"].strip(),
    )
    db.session.add(comment)
    db.session.commit()

    log_audit(current_user_id, "ADD_TASK_COMMENT", details={"task_id": task_id})

    return success_response(data=comment.to_dict(), message="Comment added", status_code=201)


# ============================================================
# GET TASK STATS (Dashboard)
# ============================================================
@tasks_bp.route("/stats", methods=["GET"])
@jwt_required()
def task_stats():
    """
    Get task statistics for dashboard.
    Employee: own stats. Admin: team stats. Super Admin: all stats.
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user:
        return error_response("User not found", 404)

    base_query = Task.query

    if current_user.role == "employee":
        base_query = base_query.filter_by(assigned_to=current_user_id)
    elif current_user.role == "admin":
        base_query = base_query.filter(
            db.or_(Task.assigned_by == current_user_id, Task.assigned_to == current_user_id)
        )

    total = base_query.count()
    pending = base_query.filter_by(status="pending").count()
    in_progress = base_query.filter_by(status="in_progress").count()
    completed = base_query.filter_by(status="completed").count()
    on_hold = base_query.filter_by(status="on_hold").count()
    cancelled = base_query.filter_by(status="cancelled").count()

    # Overdue tasks
    overdue = base_query.filter(
        Task.due_date < date.today(),
        Task.status.in_(["pending", "in_progress"])
    ).count()

    # Urgent tasks
    urgent = base_query.filter_by(priority="urgent", status__in=["pending", "in_progress"]).count() if False else \
        base_query.filter(Task.priority == "urgent", Task.status.in_(["pending", "in_progress"])).count()

    return success_response(data={
        "total": total,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "on_hold": on_hold,
        "cancelled": cancelled,
        "overdue": overdue,
        "urgent": urgent,
        "completion_rate": round((completed / total * 100), 1) if total > 0 else 0,
    })