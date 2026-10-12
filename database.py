"""
database.py - everything that talks to MongoDB.

MongoDB creates the database and the collections AUTOMATICALLY the first
time we insert data, so you do not have to create anything by hand.
"""

import os
from datetime import datetime, timedelta
from pymongo import MongoClient

MONGO_URL = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DATABASE_NAME = "smartcart_db"
CACHE_HOURS = 24  # how long a saved search stays "fresh"

# ---------- Connection ----------
client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
db = client[DATABASE_NAME]

products_cache = db["products_cache"]    # saved product lists (the cache)
search_history = db["search_history"]    # every search (cached or live)
commission_log = db["commission_log"]    # commission earned per product list


def check_connection():
    """Raises an error if MongoDB is not running."""
    client.admin.command("ping")


def clean_term(term):
    """'  Laptop BAG ' -> 'laptop bag' so the same search always matches."""
    return term.strip().lower()


def get_cached(term):
    """Return the saved product list if it is still fresh, otherwise None."""
    oldest_allowed = datetime.now() - timedelta(hours=CACHE_HOURS)
    saved = products_cache.find_one(
        {"search_term": clean_term(term), "created_at": {"$gte": oldest_allowed}},
        sort=[("created_at", -1)],  # newest first
    )
    if saved:
        return saved["products"]
    return None


def save_cache(term, products):
    products_cache.insert_one({
        "search_term": clean_term(term),
        "created_at": datetime.now(),
        "products": products,
    })


def log_search(term, number_of_results, source):
    """Record every completed search, including errors and zero-result searches."""
    search_history.insert_one({
        "search_term": clean_term(term),
        "timestamp": datetime.now(),
        "number_of_results": number_of_results,
        "source": source,
    })


def log_commission(term, products, source="live"):
    total_commission = round(sum(p["Commission_fee"] for p in products), 2)
    total_value = round(sum(p["Total_price"] for p in products), 2)
    commission_log.insert_one({
        "search_term": clean_term(term),
        "timestamp": datetime.now(),
        "number_of_products": len(products),
        "source": source,
        "total_commission": total_commission,
        "total_value": total_value,
        "products": products,
    })
