#!/usr/bin/env python3
"""Generate a styled HTML listings page from Supabase → index.html"""

import os
import re

from dotenv import load_dotenv

from render_models import to_web_listing_view_model
from web_rendering import (
    _esc as _render_esc,
    _format_date_label as _render_format_date_label,
    generate_html as render_generate_html,
)

load_dotenv()

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "index.html")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

def _parse_db_url(url: str) -> dict:
    """Parse a postgres URL, extracting credentials without percent-decoding."""
    m = re.match(
        r"postgresql(?:\+\w+)?://([^:@]+):(.+)@([^:/]+)(?::(\d+))?/([^?]+)", url
    )
    if not m:
        return {"conninfo": url}
    user, password, host, port, dbname = m.groups()
    params = {"user": user, "password": password, "host": host, "dbname": dbname}
    if port:
        params["port"] = int(port)
    return params


def get_listings() -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row

    if not SUPABASE_DB_URL:
        raise RuntimeError("SUPABASE_DB_URL environment variable is not set.")

    conn = psycopg.connect(**_parse_db_url(SUPABASE_DB_URL), row_factory=dict_row)
    cur = conn.execute(
        """
        SELECT hash, shop, artist, title, format, signed_by, signature_location,
               price, url, image_url, first_seen::date AS date_added,
               first_seen
        FROM listings
        ORDER BY first_seen DESC
        """
    )
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "hash":               row["hash"] or "",
            "shop":               row["shop"] or "",
            "artist":             row["artist"] or "",
            "title":              row["title"] or "",
            "format":             row["format"] or "unknown",
            "signed_by":          row["signed_by"] or "unknown",
            "signature_location": row["signature_location"] or "unknown",
            "price":              row["price"] or "",
            "url":                row["url"] or "",
            "image_url":          row["image_url"] or "",
            "date_added":         str(row["date_added"]) if row["date_added"] else "",
        })
    return result


def _esc(s: str) -> str:
    return _render_esc(s)


def _format_date_label(iso: str) -> str:
    return _render_format_date_label(iso)


def generate_html(listings: list[dict]) -> str:
    view_models = [to_web_listing_view_model(listing) for listing in listings]
    return render_generate_html(view_models)


def main() -> None:
    print("Reading listings from Supabase…")
    listings = get_listings()
    print(f"Found {len(listings)} listings.")

    html = generate_html(listings)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Written → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
