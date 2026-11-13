"""Load DummyJSON products into PostgreSQL (fast track step F4).

Run from the repository's top folder, with the SSH tunnel open:

    python practice/load_products.py

Running it twice should leave the same number of rows,
with newer fetched_at times. That proves it updates rather than duplicates.
"""

import os
import time

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

API_URL = "https://dummyjson.com/products"
PAGE_SIZE = 50  # how many products to ask for per request

# Insert a product; if one with the same id already exists, update it instead.
# EXCLUDED means "the values we just tried to insert".
UPSERT_SQL = """
INSERT INTO products (
    id, title, description, category, brand, price,
    discount_percentage, rating, stock, tags, raw, fetched_at
) VALUES (
    %(id)s, %(title)s, %(description)s, %(category)s, %(brand)s, %(price)s,
    %(discount_percentage)s, %(rating)s, %(stock)s, %(tags)s, %(raw)s, now()
)
ON CONFLICT (id) DO UPDATE SET
    title               = EXCLUDED.title,
    description         = EXCLUDED.description,
    category            = EXCLUDED.category,
    brand               = EXCLUDED.brand,
    price               = EXCLUDED.price,
    discount_percentage = EXCLUDED.discount_percentage,
    rating              = EXCLUDED.rating,
    stock               = EXCLUDED.stock,
    tags                = EXCLUDED.tags,
    raw                 = EXCLUDED.raw,
    fetched_at          = now();
"""


def get_page(skip):
    """Fetch one page of products, retrying a few times on temporary errors."""
    for attempt in range(1, 4):
        response = requests.get(
            API_URL,
            params={"limit": PAGE_SIZE, "skip": skip},
            timeout=30,
        )
        # 429 = too many requests; 5xx = the server had a problem. Both are worth retrying.
        if response.status_code in (429, 500, 502, 503, 504):
            wait = 2 ** attempt
            print(f"Got {response.status_code}, waiting {wait}s before retrying...")
            time.sleep(wait)
            continue
        response.raise_for_status()  # any other error stops the script with a clear message
        return response.json()
    raise RuntimeError(f"Gave up fetching the page starting at {skip}")


def fetch_all_products():
    """Walk through every page until we have all products."""
    products = []
    skip = 0
    while True:
        page = get_page(skip)
        batch = page["products"]
        products.extend(batch)
        skip += len(batch)
        print(f"  fetched {skip} of {page['total']}")
        if not batch or skip >= page["total"]:
            return products


def to_row(product):
    """Map one API product (camelCase names) to our table's columns (snake_case).

    .get() returns None when a field is missing, instead of crashing.
    """
    return {
        "id": product["id"],
        "title": product["title"],
        "description": product.get("description"),
        "category": product.get("category"),
        "brand": product.get("brand"),
        "price": product.get("price"),
        "discount_percentage": product.get("discountPercentage"),
        "rating": product.get("rating"),
        "stock": product.get("stock"),
        "tags": product.get("tags") or None,
        "raw": Jsonb(product),
    }


def main():
    load_dotenv()  # reads DATABASE_URL from your .env file
    database_url = os.environ["DATABASE_URL"]

    print("Fetching products from DummyJSON...")
    products = fetch_all_products()
    rows = [to_row(p) for p in products]

    # The "with" block commits the changes if everything succeeds,
    # and rolls them back if anything fails part-way.
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, rows)
            cur.execute("SELECT count(*), max(fetched_at) FROM products")
            count, latest = cur.fetchone()

    print(f"Done. The table now holds {count} products; latest fetch at {latest}.")


if __name__ == "__main__":
    main()
