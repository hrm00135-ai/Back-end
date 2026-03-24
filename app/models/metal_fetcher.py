import os
import threading
import time
import requests
from datetime import datetime, date
from app.extensions import db
from app.models.metals import MetalPrice, MetalPriceHistory

METAL_API_URL = "https://www.goldapi.io/api"
METAL_API_KEY = os.environ.get("METAL_API_KEY") 

def fetch_from_api():
    """Fetch live prices from GoldAPI.io."""
    if not METAL_API_KEY:
        print("[METAL FETCH ERROR] API key is missing. Check your .env file.")
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
                
                # Try to get the 24k gram price directly
                price_per_gram = data.get("price_gram_24k")
                
                # Fallback: If 'price_gram_24k' is missing (common for Silver/Platinum), 
                # calculate it using the standard Troy Ounce 'price'
                if not price_per_gram:
                    price_per_oz = data.get("price", 0)
                    price_per_gram = price_per_oz / 31.1034768  # 1 Troy Ounce = 31.1034768 grams

                if price_per_gram:
                    prices.append({
                        "metal": name,
                        "purity": "24K" if name == "gold" else "999",
                        "price_per_gram": round(price_per_gram, 2),
                        "source": "goldapi.io",
                    })
            else:
                print(f"[METAL FETCH ERROR] {name} returned status {resp.status_code}: {resp.text}")
                
        except Exception as e:
            print(f"[METAL FETCH ERROR] {name} request failed: {e}")

    return prices if prices else None