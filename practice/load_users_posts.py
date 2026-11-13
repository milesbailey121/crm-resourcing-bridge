import os
import time

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

USERS_URL = "https://jsonplaceholder.typicode.com/users/"

POSTS_URL = "https://jsonplaceholder.typicode.com/posts/"

UPSERT_USERS_SQL = """
INSERT INTO users (
    id, name, username, email, company_name, raw, fetched_at
) VALUES (
    %(id)s, %(name)s, %(username)s,%(email)s, %(company_name)s, %(raw)s, now()
)
ON CONFLICT (id) DO UPDATE SET
    id               = EXCLUDED.id,
    name         = EXCLUDED.name,
    username            = EXCLUDED.username,
    email               = EXCLUDED.email,
    company_name               = EXCLUDED.company_name,
    raw                 = EXCLUDED.raw,
    fetched_at          = now();
"""

UPSERT_POSTS_SQL = """
INSERT INTO posts (
    id, user_id, title, body, raw, fetched_at
) VALUES (
    %(id)s, %(user_id)s, %(title)s, %(body)s, %(raw)s, now()
)
ON CONFLICT (id) DO UPDATE SET
    id               = EXCLUDED.id,
    user_id         = EXCLUDED.user_id,
    title            = EXCLUDED.title,
    body               = EXCLUDED.body,
    raw                 = EXCLUDED.raw,
    fetched_at          = now();
"""




def user_to_row(user):
    """Map one API user to our table's columns."""
    return {
        "id": user["id"],
        "name": user["name"],
        "username": user.get("username"),
        "email": user.get("email"),
        "company_name": user.get('company', {}).get('name'),
        "raw": Jsonb(user)
    }

def post_to_row(post):
    """Map one API post to our table columns"""
    return {
        "id": post["id"],
        "user_id": post["userId"],
        "title": post.get("title"),
        "body": post.get("body"),
        "raw": Jsonb(post)
    }

def main():
    load_dotenv()  # reads DATABASE_URL from your .env file
    database_url = os.environ["DATABASE_URL"]

    user_response = requests.get(
                USERS_URL,
                timeout=30)

    
    for u in list(user_response.json()):
        print(u.keys())

    user_rows = [user_to_row(p) for p in user_response.json()]


    post_response = requests.get(
        POSTS_URL,
        timeout=30
    )

    for u in list(post_response.json()):
        print(u.keys())

    post_rows = [post_to_row(p) for p in post_response.json()]

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_USERS_SQL, user_rows)   # users first: posts depend on them
            cur.executemany(UPSERT_POSTS_SQL, post_rows)
            cur.execute("SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM posts)")
            user_count, post_count = cur.fetchone()

    print(f"Done. {user_count} users and {post_count} posts in the database.")

if __name__ == "__main__":
    main()