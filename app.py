"""
app.py - the web application (Flask).

Run it with:   python app.py
Then open:     http://127.0.0.1:5000
"""

import os
import re
from pathlib import Path


import requests
from openpyxl import Workbook
from flask import Flask, abort, render_template, request, send_file, send_from_directory

import database
from scraper import search_amazon, sample_products

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

app = Flask(__name__)


def add_commission(products):
    """Add Commission_fee (10%) and Total_price to every product."""
    for p in products:
        p["Commission_fee"] = round(p["Product_Price"] * COMMISSION_RATE, 2)
        p["Total_price"] = round(p["Product_Price"] + p["Commission_fee"], 2)
    return products


def download_pictures(products, term):
    """Save each product picture in Online_Pictures and store the file name."""
    safe_term = re.sub(r"[^a-zA-Z0-9]+", "_", term.strip().lower())
    for number, p in enumerate(products, start=1):
        existing_name = p.get("Product_picture_name", "")
        if existing_name and (PICTURE_FOLDER / existing_name).is_file():
            continue
        p["Product_picture_name"] = ""
        if not p["image_url"]:
            continue
        file_name = f"{safe_term}_{number}.jpg"
        try:
            image = requests.get(p["image_url"], timeout=10)
            image.raise_for_status()
            if not image.headers.get("Content-Type", "").startswith("image/"):
                continue
            (PICTURE_FOLDER / file_name).write_bytes(image.content)
            p["Product_picture_name"] = file_name
        except requests.exceptions.RequestException:
            pass  # picture failed, continue with the next product
    return products


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
                database.log_commission(term, products, source)
                try:
                    excel_path = save_excel(products)
                except (OSError, PermissionError, ValueError) as error:
                    message = f"Products were found, but the Excel file could not be saved: {error}"

            # Keep the attempted search, including zero-result searches, in history.
            database.log_search(term, len(products), source or "error")

    return render_template("index.html", products=products, term=term,
                           source=source, message=message, excel_path=excel_path)


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