from datetime import date, datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.payment import (
    EmployeePaymentConfig,
    PaymentTransaction,
    WageType,
    PaymentMethod,
    PaymentStatus,
)
from app.services.earnings_calculator import get_balance_summary, calculate_earnings

# ── Adjust to your User model path ──────────────────────────────────────────
from app.models.user import User  # noqa

payments_bp = Blueprint("payments", __name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _admin_required():
    """Return (user, None) if admin/super_admin, else (None, error_response)."""
    identity = get_jwt_identity()
    user = User.query.get(identity)
    if not user or user.role not in ("admin", "super_admin"):
        return None, (jsonify({"status": "error", "message": "Admin access required"}), 403)
    return user, None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _enrich_transaction(tx: PaymentTransaction) -> dict:
    """Add employee and admin names to a transaction dict."""
    d = tx.to_dict()
    emp   = User.query.get(tx.employee_id)
    admin = User.query.get(tx.paid_by)
    d["employee_name"] = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
    d["paid_by_name"]  = f"{admin.first_name} {admin.last_name}" if admin else "Unknown"
    return d


# ─────────────────────────────────────────────────────────────────────────────
#  Payment Config (wage type & amount)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/config/<int:employee_id>", methods=["GET"])
@jwt_required()
def get_payment_config(employee_id: int):
    """GET /api/payments/config/<employee_id> — fetch wage config."""
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
    """
    POST /api/payments/config/<employee_id>
    Body:
        {
            "wage_type":      "monthly_salary" | "daily_wage" | "per_task",
            "wage_amount":    1500.00,
            "effective_from": "2025-01-01",   (optional, defaults to today)
            "notes":          "..."            (optional)
        }
    Deactivates any existing active config and creates a new one.
    """
    admin, err = _admin_required()
    if err:
        return err

    body = request.get_json(silent=True) or {}

    # Validate wage_type
    try:
        wage_type = WageType(body.get("wage_type", ""))
    except ValueError:
        return jsonify({
            "status": "error",
            "message": f"wage_type must be one of: {[e.value for e in WageType]}"
        }), 400

    wage_amount = body.get("wage_amount")
    if wage_amount is None or float(wage_amount) < 0:
        return jsonify({"status": "error", "message": "wage_amount must be >= 0"}), 400

    effective_from = _parse_date(body.get("effective_from")) or date.today()

    # Deactivate old config
    EmployeePaymentConfig.query.filter_by(
        user_id=employee_id, is_active=True
    ).update({"is_active": False})

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

    return jsonify({
        "status":  "success",
        "message": "Payment config saved",
        "data":    config.to_dict(),
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
#  Earnings / Balance Summary
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/summary/<int:employee_id>", methods=["GET"])
@jwt_required()
def payment_summary(employee_id: int):
    """
    GET /api/payments/summary/<employee_id>
    Query params: from_date=YYYY-MM-DD  &  to_date=YYYY-MM-DD  (both optional)

    Returns total_earned / total_paid / remaining and work summary.
    """
    admin, err = _admin_required()
    if err:
        return err

    from_date = _parse_date(request.args.get("from_date"))
    to_date   = _parse_date(request.args.get("to_date"))

    emp = User.query.get(employee_id)
    if not emp:
        return jsonify({"status": "error", "message": "Employee not found"}), 404

    summary = get_balance_summary(employee_id, from_date, to_date)
    summary["employee_name"] = f"{emp.first_name} {emp.last_name}"

    return jsonify({"status": "success", "data": summary}), 200


# ─────────────────────────────────────────────────────────────────────────────
#  Work-done summary (separate endpoint for granular data)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/work-summary/<int:employee_id>", methods=["GET"])
@jwt_required()
def work_summary(employee_id: int):
    """
    GET /api/payments/work-summary/<employee_id>
    Query params: from_date, to_date
    """
    admin, err = _admin_required()
    if err:
        return err

    from_date = _parse_date(request.args.get("from_date"))
    to_date   = _parse_date(request.args.get("to_date"))

    earnings = calculate_earnings(employee_id, from_date, to_date)
    return jsonify({"status": "success", "data": earnings}), 200


# ─────────────────────────────────────────────────────────────────────────────
#  Payment History
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/history/<int:employee_id>", methods=["GET"])
@jwt_required()
def payment_history(employee_id: int):
    """
    GET /api/payments/history/<employee_id>
    Query params: page (default 1), per_page (default 20)
    """
    admin, err = _admin_required()
    if err:
        return err

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
#  Record a Payment
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/pay", methods=["POST"])
@jwt_required()
def record_payment():
    """
    POST /api/payments/pay
    Body:
        {
            "employee_id":    5,
            "amount":         5000.00,
            "payment_date":   "2025-03-01",
            "payment_method": "cash" | "bank" | "upi",
            "reference_note": "March advance"   (optional)
        }
    """
    admin, err = _admin_required()
    if err:
        return err

    body = request.get_json(silent=True) or {}

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
        return jsonify({
            "status": "error",
            "message": f"payment_method must be one of: {[m.value for m in PaymentMethod]}"
        }), 400

    amount = float(body["amount"])
    if amount <= 0:
        return jsonify({"status": "error", "message": "Amount must be > 0"}), 400

    payment_date = _parse_date(body["payment_date"])
    if not payment_date:
        return jsonify({"status": "error", "message": "Invalid payment_date (use YYYY-MM-DD)"}), 400

    tx = PaymentTransaction(
        employee_id    = employee_id,
        paid_by        = admin.id,
        amount         = amount,
        payment_date   = payment_date,
        payment_method = payment_method,
        reference_note = body.get("reference_note"),
        status         = PaymentStatus.COMPLETED,
    )
    db.session.add(tx)
    db.session.commit()

    # Return updated balance in same response for UI convenience
    summary = get_balance_summary(employee_id)

    return jsonify({
        "status":  "success",
        "message": "Payment recorded",
        "data": {
            "transaction":      _enrich_transaction(tx),
            "updated_balance":  summary,
        },
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
#  Reverse / Correct a Payment  (soft delete)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/reverse/<int:transaction_id>", methods=["POST"])
@jwt_required()
def reverse_payment(transaction_id: int):
    """
    POST /api/payments/reverse/<transaction_id>
    Body: { "reason": "Entered wrong amount" }
    """
    admin, err = _admin_required()
    if err:
        return err

    tx = PaymentTransaction.query.get(transaction_id)
    if not tx:
        return jsonify({"status": "error", "message": "Transaction not found"}), 404
    if tx.status == PaymentStatus.REVERSED:
        return jsonify({"status": "error", "message": "Already reversed"}), 400

    body = request.get_json(silent=True) or {}
    tx.status         = PaymentStatus.REVERSED
    tx.reversal_reason = body.get("reason", "")
    db.session.commit()

    return jsonify({"status": "success", "message": "Payment reversed", "data": tx.to_dict()}), 200


# ─────────────────────────────────────────────────────────────────────────────
#  All Employees Balance Overview  (for admin dashboard widget)
# ─────────────────────────────────────────────────────────────────────────────

@payments_bp.route("/overview", methods=["GET"])
@jwt_required()
def payments_overview():
    """
    GET /api/payments/overview
    Returns a balance row for every active employee.
    Heavy endpoint — cache if needed.
    """
    admin, err = _admin_required()
    if err:
        return err

    employees = User.query.filter_by(role="employee", is_active=True).all()
    results   = []

    for emp in employees:
        summary = get_balance_summary(emp.id)
        results.append({
            "employee_id":   emp.id,
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "total_earned":  summary["total_earned"],
            "total_paid":    summary["total_paid"],
            "remaining":     summary["remaining"],
            "wage_type":     summary["wage_type"],
        })

    # Sort by highest outstanding balance first
    results.sort(key=lambda r: r["remaining"], reverse=True)

    return jsonify({"status": "success", "data": results}), 200
