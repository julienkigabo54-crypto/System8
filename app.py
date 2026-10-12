"""
app.py - the web application (Flask).

Run it with:   python app.py
Then open:     http://127.0.0.1:5000
"""

import math
import os
import re
from pathlib import Path


import requests
from openpyxl import Workbook
from flask import Flask, abort, jsonify, render_template, request, send_file, send_from_directory

import database
from scraper import HEADERS, search_amazon, sample_products

# Set these environment variables to personalize the exported workbook name.
FIRST_NAME = os.getenv("SMARTCART_FIRST_NAME", "YourFirstName")
LAST_NAME = os.getenv("SMARTCART_LAST_NAME", "LastName")
REGISTRATION_NUMBER = os.getenv("SMARTCART_REGISTRATION_NUMBER", "RegistrationNumber")

# If Amazon blocks you, show clearly-labelled sample data instead of an error.
# Set to False if you only want real Amazon data.
USE_SAMPLE_IF_BLOCKED = os.getenv("SMARTCART_USE_SAMPLE_IF_BLOCKED", "false").lower() == "true"

COMMISSION_RATE = 0.10
BASE_FOLDER = Path(__file__).parent
PICTURE_FOLDER = BASE_FOLDER / "Online_Pictures"
PICTURE_FOLDER.mkdir(exist_ok=True)

# Picture types we accept, and the file extension each one is saved with.
IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_PICTURE_BYTES = 5 * 1024 * 1024

# What is stored for each product in the commission_log.
LOG_FIELDS = (
    "Product_Name",
    "Product_Price",
    "Commission_fee",
    "Total_price",
    "global_rating",
    "retailer_name",
    "Retailer_email",
    "Product_picture_name",
)
MAX_LOG_PRODUCTS = 50

app = Flask(__name__)


def add_commission(products):
    """Add Commission_fee (10%) and Total_price to every product."""
    for p in products:
        p["Commission_fee"] = round(p["Product_Price"] * COMMISSION_RATE, 2)
        p["Total_price"] = round(p["Product_Price"] + p["Commission_fee"], 2)
    return products


def download_pictures(products, term):
    """Save each product picture in Online_Pictures and store the file name."""
    safe_term = re.sub(r"[^a-zA-Z0-9]+", "_", term.strip().lower()).strip("_")[:60] or "product"
    for number, p in enumerate(products, start=1):
        existing_name = p.get("Product_picture_name", "")
        if existing_name and (PICTURE_FOLDER / existing_name).is_file():
            continue
        p["Product_picture_name"] = ""
        if not p.get("image_url"):
            continue
        try:
            image = requests.get(p["image_url"], headers=HEADERS, timeout=10)
            image.raise_for_status()
            content_type = image.headers.get("Content-Type", "").split(";")[0].strip().lower()
            extension = IMAGE_TYPES.get(content_type)
            if not extension or not image.content or len(image.content) > MAX_PICTURE_BYTES:
                continue  # not a usable picture, so the card shows the placeholder
            file_name = f"{safe_term}_{number}{extension}"
            (PICTURE_FOLDER / file_name).write_bytes(image.content)
            p["Product_picture_name"] = file_name
        except (requests.exceptions.RequestException, OSError):
            pass  # picture failed, continue with the next product
    return products


def build_log_payload(term, source, products):
    """The data the 'Save commission log' button sends back to the server."""
    return {
        "term": term,
        "source": source,
        "products": [{field: p.get(field, "") for field in LOG_FIELDS} for p in products],
    }


def save_excel(products):
    """Save the list on the Desktop as an Excel file."""
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)

    file_path = desktop / f"{FIRST_NAME}_{LAST_NAME}_{REGISTRATION_NUMBER}.xlsx"

    columns = [
        "Product_Name",
        "Product_Price",
        "Commission_fee",
        "Total_price",
        "global_rating",
        "retailer_name",
        "Retailer_email",
        "Product_picture_name"
    ]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Products"

    # Write column headings
    sheet.append(columns)

    # Write product data
    for product in products:
        sheet.append([product.get(column, "") for column in columns])

    workbook.save(file_path)

    return str(file_path)


@app.route("/", methods=["GET", "POST"])
def index():
    products = []
    message = ""
    source = ""
    excel_path = ""
    term = ""
    log_payload = None

    if request.method == "POST":
        term = request.form.get("product", "").strip()

        if not term:
            message = "Please enter a product name."
        else:
            try:
                database.check_connection()
            except Exception:
                return render_template(
                    "index.html", products=[], term=term, source="", excel_path="",
                    message="MongoDB is not running. Start MongoDB and try again.")

            # 1) Look in the cache first
            cached = database.get_cached(term)
            if cached is not None:
                products = cached
                source = "cache"
            else:
                # 2) Not cached -> search Amazon
                try:
                    products = search_amazon(term)
                    source = "live"
                except Exception as error:
                    if USE_SAMPLE_IF_BLOCKED:
                        products = sample_products(term)
                        source = "sample"
                        message = f"{error} Showing sample demo data instead."
                    else:
                        message = str(error)

            if products:
                products = add_commission(products)
                products = download_pictures(products, term)
                # Sample data is never cached; the next search tries Amazon again.
                if source == "live":
                    database.save_cache(term, products)
                # The commission log is saved with the "Save commission log" button.
                log_payload = build_log_payload(term, source, products)
                try:
                    excel_path = save_excel(products)
                except (OSError, PermissionError, ValueError) as error:
                    message = f"Products were found, but the Excel file could not be saved: {error}"

            # Keep the attempted search, including zero-result searches, in history.
            database.log_search(term, len(products), source or "error")

    return render_template("index.html", products=products, term=term,
                           source=source, message=message, excel_path=excel_path,
                           log_payload=log_payload)


@app.route("/save-commission", methods=["POST"])
def save_commission():
    """Save the product list shown on the page to the commission_log collection."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, message="There is no product list to save."), 400

    term = str(data.get("term", "")).strip()
    source = data.get("source") if data.get("source") in ("cache", "live", "sample") else "live"
    submitted = data.get("products")
    if not term or not isinstance(submitted, list) or not 0 < len(submitted) <= MAX_LOG_PRODUCTS:
        return jsonify(ok=False, message="There is no product list to save."), 400

    products = []
    for item in submitted:
        try:
            name = str(item["Product_Name"]).strip()
            price = float(item["Product_Price"])
            rating = float(item.get("global_rating") or 0)
        except (KeyError, TypeError, ValueError, AttributeError):
            return jsonify(ok=False, message="The product list is not valid."), 400
        if not name or not math.isfinite(price) or price <= 0:
            return jsonify(ok=False, message="The product list is not valid."), 400
        products.append({
            "Product_Name": name[:300],
            "Product_Price": round(price, 2),
            "global_rating": rating if math.isfinite(rating) else 0.0,
            "retailer_name": str(item.get("retailer_name", ""))[:100],
            "Retailer_email": str(item.get("Retailer_email", "N/A"))[:100],
            "Product_picture_name": os.path.basename(str(item.get("Product_picture_name", ""))),
        })

    # The fee and total are always recalculated here, never taken from the browser.
    add_commission(products)

    try:
        database.check_connection()
    except Exception:
        return jsonify(ok=False, message="MongoDB is not running. Start MongoDB and try again."), 503
    try:
        summary = database.log_commission(term, products, source)
    except Exception:
        return jsonify(ok=False, message="The commission log could not be saved. Please try again."), 500

    message = (
        f"Saved to commission_log: {summary['number_of_products']} products, "
        f"${summary['total_commission']:.2f} commission, ${summary['total_value']:.2f} total price."
    )
    return jsonify(ok=True, message=message, **summary)


@app.route("/pictures/<path:file_name>")
def pictures(file_name):
    return send_from_directory(PICTURE_FOLDER, file_name)


@app.route("/download-excel")
def download_excel():
    file_name = f"{FIRST_NAME}_{LAST_NAME}_{REGISTRATION_NUMBER}.xlsx"
    file_path = Path.home() / "Desktop" / file_name
    if not file_path.is_file():
        abort(404)
    return send_file(file_path, as_attachment=True, download_name=file_name)


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )