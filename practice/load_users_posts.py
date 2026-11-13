import os
import time

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

USERS_URL = "https://jsonplaceholder.typicode.com/users/"

POSTS_URL = "https://jsonplaceholder.typicode.com/posts/"




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

    user_response = requests.get(
                USERS_URL,
                timeout=30)

    
    print(user_response.json())
    # user_rows = [to_row(p) for p in products]

    # # The "with" block commits the changes if everything succeeds,
    # # and rolls them back if anything fails part-way.
    # with psycopg.connect(database_url) as conn:
    #     with conn.cursor() as cur:
    #         cur.executemany(UPSERT_SQL, rows)
    #         cur.execute("SELECT count(*), max(fetched_at) FROM products")
    #         count, latest = cur.fetchone()

    # print(f"Done. The table now holds {count} products; latest fetch at {latest}.")

if __name__ == "__main__":
    main()