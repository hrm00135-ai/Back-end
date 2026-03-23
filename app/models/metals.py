from datetime import datetime
from app.extensions import db


class MetalPrice(db.Model):
    """Cached metal prices - updated periodically by background job."""
    __tablename__ = "metal_prices"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    metal = db.Column(db.String(20), nullable=False, index=True)  # gold, silver, platinum, palladium
    purity = db.Column(db.String(20), nullable=True)  # 24K, 22K, 18K, 999, 925
    price_per_gram = db.Column(db.Float, nullable=False)
    price_per_10gram = db.Column(db.Float, nullable=True)
    price_per_kg = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(5), default="INR")
    source = db.Column(db.String(100), nullable=True)
    fetched_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "metal": self.metal,
            "purity": self.purity,
            "price_per_gram": self.price_per_gram,
            "price_per_10gram": self.price_per_10gram,
            "price_per_kg": self.price_per_kg,
            "currency": self.currency,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class MetalPriceHistory(db.Model):
    """Historical metal prices for charts/trends."""
    __tablename__ = "metal_price_history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    metal = db.Column(db.String(20), nullable=False, index=True)
    purity = db.Column(db.String(20), nullable=True)
    price_per_gram = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(5), default="INR")
    date = db.Column(db.Date, nullable=False, index=True)
    source = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("metal", "purity", "date", name="uq_metal_purity_date"),
    )

    def to_dict(self):
        return {
            "metal": self.metal,
            "purity": self.purity,
            "price_per_gram": self.price_per_gram,
            "date": self.date.isoformat() if self.date else None,
        }