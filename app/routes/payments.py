"""
JewelCraft HRM — Payments Routes
Full: per-task, advance, invoice upload, no-negative, employee self-access
"""

import os
from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.payment import (
    EmployeePaymentConfig,
    PaymentTransaction,
    WageType,
    PaymentMethod,
    PaymentStatus,
)
from app.models.task import Task
from app.services.earnings_calculator import get_balance_summary, calculate_earnings
from app.models.user import User

payments_bp = Blueprint("payments", __name__)

INVOICE_ALLOWED = {"png", "jpg", "jpeg", "pdf", "webp"}


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _admin_required():
    identity = get_jwt_identity()
    user = User.query.get(identity)
    if not user or user.role not in ("admin", "super_admin"):
        return None, (jsonify({"status": "error", "message": "Admin access required"}), 403)
    return user, None


def _get_current_user():
    identity = get_jwt_identity()
    return User.query.get(identity)


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _enrich_transaction(tx: PaymentTransaction) -> dict:
    d = tx.to_dict()
    emp   = User.query.get(tx.employee_id)
    admin = User.query.get(tx.paid_by)
    d["employee_name"] = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
    d["paid_by_name"]  = f"{admin.first_name} {admin.last_name}" if admin else "Unknown"
    return d


def _task_paid_total(task_id: int, exclude_tx_id: int = None) -> Decimal:
    """Sum of all COMPLETED payments (advance + regular) for a specific task."""
    q = (
        PaymentTransaction.query
        .with_entities(func.coalesce(func.sum(PaymentTransaction.amount), 0))
        .filter(
            PaymentTransaction.task_id == task_id,
            PaymentTransaction.status == PaymentStatus.COMPLETED,
        )
    )
    if exclude_tx_id:
        q = q.filter(PaymentTransaction.id != exclude_tx_id)
    return Decimal(str(q.scalar()))


def _save_invoice(file, tx_id: int) -> str:
    """Save invoice file and return relative path."""
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if ext not in INVOICE_ALLOWED:
        ext = "jpg"
    filename = secure_filename(f"invoice_{tx_id}.{ext}")
    folder = os.path.join(current_app.config.get("UPLOAD_FOLDER", "uploads"), "invoices")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    file.save(path)
    return f"uploads/invoices/{filename}"


# ─────────────────────────────────────────────────────────────────────────────
#  Payment Config
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/config/<int:employee_id>", methods=["GET"])
@jwt_required()
def get_payment_config(employee_id: int):
    admin, err = _admin_required()
    if err:
        return err
    config = (
        EmployeePaymentConfig.query
        .filter_by(user_id=employee_id, is_active=True)
        .order_by(EmployeePaymentConfig.effective_from.desc())
        .first()
    )
    if not config:
        return jsonify({"status": "success", "data": None, "message": "No config set"}), 200
    return jsonify({"status": "success", "data": config.to_dict()}), 200


@payments_bp.route("/config/<int:employee_id>", methods=["POST"])
@jwt_required()
def set_payment_config(employee_id: int):
    admin, err = _admin_required()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    try:
        wage_type = WageType(body.get("wage_type", ""))
    except ValueError:
        return jsonify({"status": "error", "message": f"wage_type must be one of: {[e.value for e in WageType]}"}), 400

    wage_amount = body.get("wage_amount")
    if wage_amount is None or float(wage_amount) < 0:
        return jsonify({"status": "error", "message": "wage_amount must be >= 0"}), 400

    effective_from = _parse_date(body.get("effective_from")) or date.today()

    EmployeePaymentConfig.query.filter_by(user_id=employee_id, is_active=True).update({"is_active": False})

    config = EmployeePaymentConfig(
        user_id        = employee_id,
        wage_type      = wage_type,
        wage_amount    = wage_amount,
        effective_from = effective_from,
        is_active      = True,
        notes          = body.get("notes"),
    )
    db.session.add(config)
    db.session.commit()
    return jsonify({"status": "success", "message": "Payment config saved", "data": config.to_dict()}), 201


# ─────────────────────────────────────────────────────────────────────────────
#  Earnings / Balance Summary — Admin view (any employee)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/summary/<int:employee_id>", methods=["GET"])
@jwt_required()
def payment_summary(employee_id: int):
    """Admin or the employee themselves can access."""
    current = _get_current_user()
    if not current:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # Allow employee to access their own summary
    if current.role == "employee" and current.id != employee_id:
        return jsonify({"status": "error", "message": "Access denied"}), 403

    from_date = _parse_date(request.args.get("from_date"))
    to_date   = _parse_date(request.args.get("to_date"))

    emp = User.query.get(employee_id)
    if not emp:
        return jsonify({"status": "error", "message": "Employee not found"}), 404

    summary = get_balance_summary(employee_id, from_date, to_date)
    # Never return negative remaining to the client
    summary["remaining"] = max(0.0, summary["remaining"])
    summary["employee_name"] = f"{emp.first_name} {emp.last_name}"

    return jsonify({"status": "success", "data": summary}), 200


# ─────────────────────────────────────────────────────────────────────────────
#  My own summary / history (employee-facing, no admin required)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/my-summary", methods=["GET"])
@jwt_required()
def my_payment_summary():
    current = _get_current_user()
    if not current:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    from_date = _parse_date(request.args.get("from_date"))
    to_date   = _parse_date(request.args.get("to_date"))

    summary = get_balance_summary(current.id, from_date, to_date)
    summary["remaining"] = max(0.0, summary["remaining"])
    summary["employee_name"] = f"{current.first_name} {current.last_name}"
    return jsonify({"status": "success", "data": summary}), 200


@payments_bp.route("/my-history", methods=["GET"])
@jwt_required()
def my_payment_history():
    current = _get_current_user()
    if not current:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 15))

    pagination = (
        PaymentTransaction.query
        .filter_by(employee_id=current.id)
        .order_by(PaymentTransaction.payment_date.desc(), PaymentTransaction.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    transactions = [_enrich_transaction(tx) for tx in pagination.items]
    return jsonify({
        "status": "success",
        "data": {
            "transactions": transactions,
            "total":        pagination.total,
            "page":         pagination.page,
            "pages":        pagination.pages,
            "per_page":     per_page,
        },
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
#  Payment History (admin)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/history/<int:employee_id>", methods=["GET"])
@jwt_required()
def payment_history(employee_id: int):
    current = _get_current_user()
    if not current:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if current.role == "employee" and current.id != employee_id:
        return jsonify({"status": "error", "message": "Access denied"}), 403

    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    pagination = (
        PaymentTransaction.query
        .filter_by(employee_id=employee_id)
        .order_by(PaymentTransaction.payment_date.desc(), PaymentTransaction.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    transactions = [_enrich_transaction(tx) for tx in pagination.items]
    return jsonify({
        "status": "success",
        "data": {
            "transactions": transactions,
            "total":        pagination.total,
            "page":         pagination.page,
            "pages":        pagination.pages,
            "per_page":     per_page,
        },
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
#  Task payment details — get all payments for one task
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/task/<int:task_id>", methods=["GET"])
@jwt_required()
def task_payments(task_id: int):
    """Get all payment transactions for a specific task. Employee can see their own."""
    current = _get_current_user()
    if not current:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    task = Task.query.get(task_id)
    if not task:
        return jsonify({"status": "error", "message": "Task not found"}), 404

    # Employee can only see payments for tasks assigned to them
    if current.role == "employee" and task.assigned_to != current.id:
        return jsonify({"status": "error", "message": "Access denied"}), 403

    payments = (
        PaymentTransaction.query
        .filter_by(task_id=task_id)
        .filter(PaymentTransaction.status == PaymentStatus.COMPLETED)
        .order_by(PaymentTransaction.payment_date.desc())
        .all()
    )

    total_paid   = float(_task_paid_total(task_id))
    task_total   = float(task.payment_amount or 0)
    remaining    = max(0.0, task_total - total_paid)
    advance_paid = float(
        sum(float(p.amount) for p in payments if p.is_advance)
    )

    return jsonify({
        "status": "success",
        "data": {
            "task_payment": {
                "task_id":         task.id,
                "task_title":      task.title,
                "payment_amount":  task_total,
                "total_paid":      total_paid,
                "advance_paid":    advance_paid,
                "remaining":       remaining,
            },
            "payments": [_enrich_transaction(p) for p in payments],
        },
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
#  Task payment remaining — quick check for advance validation
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/task/<int:task_id>/balance", methods=["GET"])
@jwt_required()
def task_payment_balance(task_id: int):
    """Quick endpoint to check how much has been paid vs total for a task."""
    admin, err = _admin_required()
    if err:
        return err

    task = Task.query.get(task_id)
    if not task:
        return jsonify({"status": "error", "message": "Task not found"}), 404

    total_paid   = float(_task_paid_total(task_id))
    task_total   = float(task.payment_amount or 0)
    remaining    = max(0.0, task_total - total_paid)
    advance_paid = float(
        db.session.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
        .filter(
            PaymentTransaction.task_id == task_id,
            PaymentTransaction.is_advance == True,
            PaymentTransaction.status == PaymentStatus.COMPLETED,
        )
        .scalar()
    )

    return jsonify({
        "status": "success",
        "data": {
            "task_total":    task_total,
            "total_paid":    total_paid,
            "advance_paid":  advance_paid,
            "remaining":     remaining,
            "max_payable":   remaining,
        },
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
#  Record a Payment (admin only) — supports task_id, is_advance, invoice
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/pay", methods=["POST"])
@jwt_required()
def record_payment():
    """
    POST /api/payments/pay
    Accepts multipart/form-data OR application/json.
    For invoice upload use multipart; include invoice_file field.

    Required: employee_id, amount, payment_date, payment_method
    Optional: task_id, is_advance (bool), reference_note, invoice_file
    """
    admin, err = _admin_required()
    if err:
        return err

    # Support both JSON and form-data
    if request.content_type and "multipart" in request.content_type:
        body = request.form.to_dict()
        invoice_file = request.files.get("invoice_file")
    else:
        body = request.get_json(silent=True) or {}
        invoice_file = None

    # Validate required fields
    for field in ("employee_id", "amount", "payment_date", "payment_method"):
        if field not in body:
            return jsonify({"status": "error", "message": f"Missing field: {field}"}), 400

    employee_id = int(body["employee_id"])
    emp = User.query.get(employee_id)
    if not emp or emp.role != "employee":
        return jsonify({"status": "error", "message": "Employee not found"}), 404

    try:
        payment_method = PaymentMethod(body["payment_method"])
    except ValueError:
        return jsonify({"status": "error", "message": f"payment_method must be one of: {[m.value for m in PaymentMethod]}"}), 400

    # Amount validation — no negatives, no zero
    try:
        amount = float(body["amount"])
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid amount"}), 400

    if amount <= 0:
        return jsonify({"status": "error", "message": "Amount must be greater than zero"}), 400

    payment_date = _parse_date(body["payment_date"])
    if not payment_date:
        return jsonify({"status": "error", "message": "Invalid payment_date (use YYYY-MM-DD)"}), 400

    # Parse optional task / advance fields
    task_id    = int(body["task_id"]) if body.get("task_id") else None
    is_advance = str(body.get("is_advance", "false")).lower() in ("true", "1", "yes")

    # Validate task-level payment cap (no overpayment)
    if task_id:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        if task.assigned_to != employee_id:
            return jsonify({"status": "error", "message": "Task is not assigned to this employee"}), 400

        task_total  = float(task.payment_amount or 0)
        already_paid = float(_task_paid_total(task_id))
        max_payable  = max(0.0, task_total - already_paid)

        if task_total > 0 and amount > max_payable + 0.01:  # 0.01 tolerance for float
            return jsonify({
                "status":  "error",
                "message": (
                    f"Amount exceeds task balance. "
                    f"Task total: ₹{task_total:.2f}, Already paid: ₹{already_paid:.2f}, "
                    f"Max payable: ₹{max_payable:.2f}"
                ),
            }), 400

    # Create transaction
    tx = PaymentTransaction(
        employee_id    = employee_id,
        paid_by        = admin.id,
        amount         = amount,
        payment_date   = payment_date,
        payment_method = payment_method,
        reference_note = body.get("reference_note"),
        task_id        = task_id,
        is_advance     = is_advance,
        status         = PaymentStatus.COMPLETED,
    )
    db.session.add(tx)
    db.session.flush()  # get tx.id before commit for invoice path

    # Save invoice if provided
    if invoice_file and invoice_file.filename:
        try:
            invoice_path = _save_invoice(invoice_file, tx.id)
            tx.invoice_url = invoice_path
        except Exception as e:
            current_app.logger.error(f"Invoice save failed: {e}")

    db.session.commit()

    summary = get_balance_summary(employee_id)
    summary["remaining"] = max(0.0, summary["remaining"])

    return jsonify({
        "status":  "success",
        "message": "Payment recorded" + (" (Advance)" if is_advance else ""),
        "data": {
            "transaction":     _enrich_transaction(tx),
            "updated_balance": summary,
        },
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
#  Upload / Replace Invoice for existing transaction
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/pay/<int:transaction_id>/invoice", methods=["POST"])
@jwt_required()
def upload_invoice(transaction_id: int):
    """
    POST /api/payments/pay/<tx_id>/invoice
    Upload or replace the invoice slip for a payment transaction.
    """
    admin, err = _admin_required()
    if err:
        return err

    tx = PaymentTransaction.query.get(transaction_id)
    if not tx:
        return jsonify({"status": "error", "message": "Transaction not found"}), 404
    if tx.status == PaymentStatus.REVERSED:
        return jsonify({"status": "error", "message": "Cannot update a reversed transaction"}), 400

    invoice_file = request.files.get("invoice_file")
    if not invoice_file or not invoice_file.filename:
        return jsonify({"status": "error", "message": "No file provided"}), 400

    ext = invoice_file.filename.rsplit(".", 1)[-1].lower() if "." in invoice_file.filename else ""
    if ext not in INVOICE_ALLOWED:
        return jsonify({"status": "error", "message": f"File type not allowed. Use: {', '.join(INVOICE_ALLOWED)}"}), 400

    # Delete old invoice file if exists
    if tx.invoice_url:
        old_path = os.path.join(
            current_app.root_path, "..",
            current_app.config.get("UPLOAD_FOLDER", "uploads"),
            "invoices",
            os.path.basename(tx.invoice_url),
        )
        try:
            if os.path.exists(old_path):
                os.remove(old_path)
        except Exception:
            pass

    invoice_path = _save_invoice(invoice_file, tx.id)
    tx.invoice_url = invoice_path
    db.session.commit()

    return jsonify({
        "status":  "success",
        "message": "Invoice uploaded",
        "data":    _enrich_transaction(tx),
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
#  Reverse a Payment
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/reverse/<int:transaction_id>", methods=["POST"])
@jwt_required()
def reverse_payment(transaction_id: int):
    admin, err = _admin_required()
    if err:
        return err

    tx = PaymentTransaction.query.get(transaction_id)
    if not tx:
        return jsonify({"status": "error", "message": "Transaction not found"}), 404
    if tx.status == PaymentStatus.REVERSED:
        return jsonify({"status": "error", "message": "Already reversed"}), 400

    body = request.get_json(silent=True) or {}
    tx.status          = PaymentStatus.REVERSED
    tx.reversal_reason = body.get("reason", "")
    db.session.commit()

    return jsonify({"status": "success", "message": "Payment reversed", "data": tx.to_dict()}), 200


# ─────────────────────────────────────────────────────────────────────────────
#  All Employees Overview
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/overview", methods=["GET"])
@jwt_required()
def payments_overview():
    admin, err = _admin_required()
    if err:
        return err

    employees = User.query.filter_by(role="employee", is_active=True).all()
    results = []
    for emp in employees:
        summary = get_balance_summary(emp.id)
        results.append({
            "employee_id":   emp.id,
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "total_earned":  summary["total_earned"],
            "total_paid":    summary["total_paid"],
            "remaining":     max(0.0, summary["remaining"]),
            "wage_type":     summary["wage_type"],
        })

    results.sort(key=lambda r: r["remaining"], reverse=True)
    return jsonify({"status": "success", "data": results}), 200


# ─────────────────────────────────────────────────────────────────────────────
#  Work Summary
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/work-summary/<int:employee_id>", methods=["GET"])
@jwt_required()
def work_summary(employee_id: int):
    admin, err = _admin_required()
    if err:
        return err
    from_date = _parse_date(request.args.get("from_date"))
    to_date   = _parse_date(request.args.get("to_date"))
    earnings  = calculate_earnings(employee_id, from_date, to_date)
    return jsonify({"status": "success", "data": earnings}), 200