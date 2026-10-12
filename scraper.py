"""
scraper.py - connects to www.amazon.com, searches for a product and
returns a simple list of dictionaries.

NOTE: Amazon sometimes blocks programs (CAPTCHA). When that happens
search_amazon() raises an error and app.py shows a clear message.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_PRODUCTS = 12
DETAIL_WORKERS = 5


def to_number(text):
    """'$1,299.99' -> 1299.99"""
    cleaned = re.sub(r"[^0-9.]", "", text)
    return float(cleaned) if cleaned else 0.0


def extract_price(container):
    """Extract an Amazon price without guessing missing decimal places."""
    if container is None:
        return 0.0
    price_tag = container if "a-price" in container.get("class", []) else None
    price_tag = price_tag or container.select_one("span.a-price")
    if price_tag:
        whole = price_tag.select_one(".a-price-whole")
        fraction = price_tag.select_one(".a-price-fraction")
        if whole:
            whole_value = re.sub(r"[^0-9]", "", whole.get_text())
            fraction_value = re.sub(r"[^0-9]", "", fraction.get_text()) if fraction else "00"
            if whole_value:
                return float(f"{whole_value}.{fraction_value[:2].ljust(2, '0')}")

    offscreen = price_tag.select_one(".a-offscreen") if price_tag else None
    if not price_tag:
        offscreen = container.select_one("span.a-price span.a-offscreen")
    if offscreen:
        return to_number(offscreen.get_text(" ", strip=True))

    return 0.0


def fetch_detail_price(product_url):
    """Fetch a detail page when Amazon omits the price from a search card."""
    try:
        response = requests.get(product_url, headers=HEADERS, timeout=12)
        if response.status_code != 200 or "captcha" in response.text.lower():
            return 0.0
        soup = BeautifulSoup(response.text, "html.parser")
        for price_tag in soup.select("span.a-price"):
            if price_tag.get("data-a-color") == "base":
                price = extract_price(price_tag)
                if price > 0:
                    return price
        return extract_price(soup.select_one("#corePriceDisplay_desktop_feature_div") or soup)
    except requests.exceptions.RequestException:
        return 0.0


def search_amazon(term):
    """Search Amazon and return a list of products (without commission yet)."""
    url = "https://www.amazon.com/s"
    try:
        response = requests.get(url, params={"k": term}, headers=HEADERS, timeout=20)
    except requests.exceptions.RequestException as error:
        raise Exception("Could not connect to Amazon. Check your internet connection.") from error

    blocked_markers = ("captcha", "robot check", "automated access")
    if response.status_code != 200 or any(marker in response.text.lower() for marker in blocked_markers):
        raise Exception("Amazon blocked the request (CAPTCHA). Try again later.")

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select('div[data-component-type="s-search-result"]')

    products = []
    missing_price = []
    for item in items:
        name_tag = item.select_one("h2")
        if not name_tag:
            continue

        rating_tag = item.select_one("span.a-icon-alt")
        rating = to_number(rating_tag.get_text().split(" out")[0]) if rating_tag else 0.0
        image_tag = item.select_one("img.s-image")
        image_url = image_tag.get("src", "") if image_tag else ""
        link_tag = item.select_one("[data-cy='title-recipe'] a[href]")
        product_url = urljoin("https://www.amazon.com", link_tag["href"]) if link_tag else ""

        product = {
            "Product_Name": name_tag.get_text(strip=True),
            "Product_Price": extract_price(item),
            "global_rating": rating,
            "retailer_name": "Amazon",
            "Retailer_email": "N/A",
            "image_url": image_url,
        }
        if product["Product_Price"] > 0:
            products.append(product)
        elif product_url:
            missing_price.append((product, product_url))
        if len(products) + len(missing_price) >= MAX_PRODUCTS:
            break

    if missing_price:
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
            prices = executor.map(fetch_detail_price, (url for _, url in missing_price))
            for (product, _), price in zip(missing_price, prices):
                if price > 0:
                    product["Product_Price"] = price
                    products.append(product)

    if not products:
        if items:
            raise Exception(
                "Amazon found matching products but did not expose their prices. "
                "Please try again later or search Amazon directly."
            )
        raise Exception("Amazon returned no matching products. Try another product name.")
    return products


def sample_products(term):
    """Demo data used ONLY when Amazon blocks us and USE_SAMPLE_IF_BLOCKED is True."""
    names = ["Basic", "Plus", "Pro"]
    prices = [19.99, 34.50, 59.00]
    ratings = [4.1, 4.4, 4.7]
    return [
        {
            "Product_Name": f"{term} - {names[i]} (sample)",
            "Product_Price": prices[i],
            "global_rating": ratings[i],
            "retailer_name": "Sample Retailer",
            "Retailer_email": "N/A",
            "image_url": "",
        }
        for i in range(3)
    ]
