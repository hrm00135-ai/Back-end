import threading
import time
import requests
from datetime import datetime, date
from app.extensions import db
from app.models.metals import MetalPrice, MetalPriceHistory


# Free API options - using GoldAPI.io (free tier: 300 req/month)
# Or manual/admin entry as fallback
METAL_API_URL = "https://www.goldapi.io/api"
METAL_API_KEY = None  # Set in .env if you have one


def fetch_from_api():
    """Fetch live prices from GoldAPI.io (if API key available)."""
    if not METAL_API_KEY:
        return None

    metals = {"XAU": "gold", "XAG": "silver", "XPT": "platinum", "XPD": "palladium"}
    prices = []

    for code, name in metals.items():
        try:
            resp = requests.get(
                f"{METAL_API_URL}/{code}/INR",
                headers={"x-access-token": METAL_API_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                price_per_gram = data.get("price_gram_24k", 0)
                prices.append({
                    "metal": name,
                    "purity": "24K" if name == "gold" else "999",
                    "price_per_gram": round(price_per_gram, 2),
                    "source": "goldapi.io",
                })
        except Exception as e:
            print(f"[METAL FETCH ERROR] {name}: {e}")

    return prices if prices else None


def update_metal_prices(app, prices_data=None):
    """Update metal prices in DB. Called by scheduler or manually."""
    with app.app_context():
        if prices_data is None:
            prices_data = fetch_from_api()

        if not prices_data:
            return False

        now = datetime.utcnow()
        today = date.today()

        for p in prices_data:
            # Update current price
            existing = MetalPrice.query.filter_by(
                metal=p["metal"], purity=p.get("purity")
            ).first()

            if existing:
                existing.price_per_gram = p["price_per_gram"]
                existing.price_per_10gram = round(p["price_per_gram"] * 10, 2)
                existing.price_per_kg = round(p["price_per_gram"] * 1000, 2)
                existing.source = p.get("source", "manual")
                existing.fetched_at = now
            else:
                new_price = MetalPrice(
                    metal=p["metal"],
                    purity=p.get("purity"),
                    price_per_gram=p["price_per_gram"],
                    price_per_10gram=round(p["price_per_gram"] * 10, 2),
                    price_per_kg=round(p["price_per_gram"] * 1000, 2),
                    currency=p.get("currency", "INR"),
                    source=p.get("source", "manual"),
                    fetched_at=now,
                )
                db.session.add(new_price)

            # Add to history (one per day)
            hist = MetalPriceHistory.query.filter_by(
                metal=p["metal"], purity=p.get("purity"), date=today
            ).first()
            if not hist:
                hist = MetalPriceHistory(
                    metal=p["metal"],
                    purity=p.get("purity"),
                    price_per_gram=p["price_per_gram"],
                    date=today,
                    source=p.get("source", "manual"),
                )
                db.session.add(hist)
            else:
                hist.price_per_gram = p["price_per_gram"]

        db.session.commit()
        return True


def start_price_scheduler(app, interval_minutes=30):
    """Background thread to fetch prices periodically."""
    def run():
        while True:
            try:
                update_metal_prices(app)
                print(f"[METAL PRICES] Updated at {datetime.utcnow()}")
            except Exception as e:
                print(f"[METAL PRICES ERROR] {e}")
            time.sleep(interval_minutes * 60)

    if METAL_API_KEY:
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        print(f"[METAL PRICES] Scheduler started (every {interval_minutes} min)")
    else:
        print("[METAL PRICES] No API key set. Use manual entry or set METAL_API_KEY in .env")