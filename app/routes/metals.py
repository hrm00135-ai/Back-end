from datetime import datetime, date, timedelta
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.user import User
from app.models.metals import MetalPrice, MetalPriceHistory
from app.utils.helpers import log_audit, success_response, error_response

metals_bp = Blueprint("metals", __name__, url_prefix="/api/metals")


# ============================================================
# GET CURRENT PRICES (All roles can view)
# ============================================================
@metals_bp.route("/prices", methods=["GET"])
@jwt_required()
def get_prices():
    """Get latest cached metal prices. No external API call."""
    prices = MetalPrice.query.all()

    if not prices:
        return success_response(data=[], message="No prices available. Admin needs to add prices.")

    return success_response(data=[p.to_dict() for p in prices])


# ============================================================
# GET PRICE HISTORY (for charts)
# ============================================================
@metals_bp.route("/history", methods=["GET"])
@jwt_required()
def price_history():
    """Get price history for charts. Query: ?metal=gold&days=30"""
    metal = request.args.get("metal", "gold")
    days = request.args.get("days", 30, type=int)
    purity = request.args.get("purity")

    from_date = date.today() - timedelta(days=days)

    query = MetalPriceHistory.query.filter(
        MetalPriceHistory.metal == metal,
        MetalPriceHistory.date >= from_date,
    )
    if purity:
        query = query.filter_by(purity=purity)

    history = query.order_by(MetalPriceHistory.date.asc()).all()

    return success_response(data=[h.to_dict() for h in history])


# ============================================================
# MANUALLY SET PRICES (Admin/SA - fallback when no API key)
# ============================================================
@metals_bp.route("/prices", methods=["POST"])
@jwt_required()
def set_prices():
    """
    Manually set metal prices. Admin/SA only.
    Body: { "prices": [
        { "metal": "gold", "purity": "24K", "price_per_gram": 7500 },
        { "metal": "gold", "purity": "22K", "price_per_gram": 6875 },
        { "metal": "gold", "purity": "18K", "price_per_gram": 5625 },
        { "metal": "silver", "purity": "999", "price_per_gram": 95 },
        { "metal": "platinum", "purity": "950", "price_per_gram": 3200 },
        { "metal": "palladium", "purity": "999", "price_per_gram": 3800 }
    ]}
    """
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)

    if not current_user or current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can set prices", 403)

    data = request.get_json()
    if not data or not data.get("prices"):
        return error_response("prices array is required", 400)

    from app.models.metal_fetcher import update_metal_prices
    from flask import current_app

    prices_data = []
    for p in data["prices"]:
        if not p.get("metal") or not p.get("price_per_gram"):
            continue
        prices_data.append({
            "metal": p["metal"].lower().strip(),
            "purity": p.get("purity", "").strip() or None,
            "price_per_gram": float(p["price_per_gram"]),
            "source": "manual",
            "currency": p.get("currency", "INR"),
        })

    if not prices_data:
        return error_response("No valid price entries", 400)

    update_metal_prices(current_app._get_current_object(), prices_data)

    log_audit(current_user_id, "SET_METAL_PRICES", details={"count": len(prices_data)})

    prices = MetalPrice.query.all()
    return success_response(data=[pr.to_dict() for pr in prices], message=f"{len(prices_data)} prices updated")


# ============================================================
# QUICK CALCULATOR (for artisans)
# ============================================================
@metals_bp.route("/calculate", methods=["POST"])
@jwt_required()
def calculate_value():
    """
    Quick metal value calculator.
    Body: { "metal": "gold", "purity": "22K", "weight_grams": 10 }
    """
    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    metal = data.get("metal", "gold").lower()
    purity = data.get("purity")
    weight = data.get("weight_grams", 0)

    if not weight or weight <= 0:
        return error_response("weight_grams must be positive", 400)

    price = MetalPrice.query.filter_by(metal=metal)
    if purity:
        price = price.filter_by(purity=purity)
    price = price.first()

    if not price:
        return error_response(f"No price found for {metal} {purity or ''}", 404)

    total_value = round(price.price_per_gram * float(weight), 2)

    return success_response(data={
        "metal": metal,
        "purity": purity or price.purity,
        "weight_grams": weight,
        "price_per_gram": price.price_per_gram,
        "total_value": total_value,
        "currency": price.currency,
        "price_as_of": price.fetched_at.isoformat() if price.fetched_at else None,
    })