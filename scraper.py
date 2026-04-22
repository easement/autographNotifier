"""
Autograph Notifier
Scrapes signed records/CDs from online shops, detects new listings,
stores results in Supabase/PostgreSQL, sends email notifications.

Requires: pip install playwright beautifulsoup4 psycopg[binary] httpx python-dotenv
           playwright install chromium
"""

import asyncio
import hashlib
import os
import re
import smtplib
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

from email_rendering import (
    _format_badge_email as _render_format_badge_email,
    _shop_block_html as _render_shop_block_html,
    build_email_html as _render_build_email_html,
)
from render_models import to_email_listing_view_model

load_dotenv()


# ─── Data Model ───────────────────────────────────────────────────────────────

@dataclass
class Listing:
    shop: str
    artist: str
    title: str
    format: str              # 'LP' | 'CD' | '7"' | '10"' | 'cassette' | 'unknown'
    signed_by: str           # 'band' | 'solo' | 'unknown'
    signature_location: str  # 'cover' | 'insert' | 'booklet' | 'sleeve' | 'label' | 'unknown'
    price: Optional[str]
    url: str
    image_url: Optional[str]
    description: Optional[str]
    hash: str = field(default="", init=False)

    def __post_init__(self):
        key = f"{self.shop}|{self.url}".lower().strip()
        self.hash = hashlib.sha256(key.encode()).hexdigest()[:16]


# ─── Database ─────────────────────────────────────────────────────────────────

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


def init_db():
    import psycopg
    if not SUPABASE_DB_URL:
        raise RuntimeError("SUPABASE_DB_URL environment variable is not set.")
    conn = psycopg.connect(**_parse_db_url(SUPABASE_DB_URL))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS public.listings (
            hash                TEXT PRIMARY KEY,
            shop                TEXT,
            artist              TEXT,
            title               TEXT,
            format              TEXT,
            signed_by           TEXT,
            signature_location  TEXT,
            price               TEXT,
            url                 TEXT,
            image_url           TEXT,
            description         TEXT,
            first_seen          TIMESTAMPTZ,
            last_seen           TIMESTAMPTZ,
            archived            BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    # Migrate existing tables that predate the archived column
    conn.execute("""
        ALTER TABLE listings ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE
    """)
    conn.commit()
    return conn


def upsert_listings(conn, listings: list[Listing], run_time: datetime) -> list[Listing]:
    """Insert new listings, update last_seen for existing ones. Returns NEW listings only."""
    new_listings = []
    for lst in listings:
        existing = conn.execute(
            "SELECT hash FROM listings WHERE hash = %s", (lst.hash,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE listings SET last_seen = %s, archived = FALSE WHERE hash = %s",
                (run_time, lst.hash),
            )
        else:
            conn.execute(
                """INSERT INTO listings
                    (hash, shop, artist, title, format, signed_by, signature_location,
                     price, url, image_url, description, first_seen, last_seen, archived)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)""",
                (lst.hash, lst.shop, lst.artist, lst.title, lst.format, lst.signed_by,
                 lst.signature_location, lst.price, lst.url, lst.image_url,
                 lst.description, run_time, run_time),
            )
            new_listings.append(lst)
    conn.commit()
    return new_listings


def archive_stale_listings(conn, successful_shops: list[str], run_time: datetime) -> int:
    """Archive listings from shops that scraped successfully but weren't seen this run.

    Only touches shops that returned data — if a scraper errored, its listings are left alone.
    Returns the number of newly archived listings.
    """
    if not successful_shops:
        return 0
    result = conn.execute(
        """
        UPDATE listings
           SET archived = TRUE
         WHERE shop = ANY(%s)
           AND last_seen < %s
           AND archived = FALSE
        """,
        (successful_shops, run_time),
    )
    conn.commit()
    count = result.rowcount if result.rowcount is not None else 0
    return count


def deduplicate_listings(listings: list[Listing]) -> list[Listing]:
    seen: set[str] = set()
    out: list[Listing] = []
    for lst in listings:
        if lst.hash not in seen:
            seen.add(lst.hash)
            out.append(lst)
    return out


# ─── Metadata Parser ──────────────────────────────────────────────────────────

def parse_signed_metadata(title: str, description: str) -> tuple[str, str, str]:
    """Extract (format, signed_by, signature_location) from title + description text."""
    combined = f"{title} {description or ''}".lower()

    # ── Format ──
    fmt = "unknown"
    if re.search(r'\b7\s*["\u201c\u201d]|7\s*inch\b|7-inch\b', combined):
        fmt = '7"'
    elif re.search(r'\b10\s*["\u201c\u201d]|10\s*inch\b|10-inch\b', combined):
        fmt = '10"'
    elif re.search(r'\b12\s*["\u201c\u201d]|12\s*inch\b|12-inch\b', combined):
        fmt = '12"'
    elif re.search(r'\bcassette\b|\btape\b', combined):
        fmt = 'cassette'
    elif re.search(r'\bcd\b|\bcompact\s*disc\b', combined):
        fmt = 'CD'
    elif re.search(r'\blp\b|\bvinyl\b|\balbum\b|\brecord\b', combined):
        fmt = 'LP'

    # ── Signed by ──
    signed_by = "unknown"
    band_patterns = [
        r'(signed|autographed)\s+by\s+(the\s+)?(full\s+)?(entire\s+)?(band|group|whole\s+band)',
        r'all\s+(four|three|five|six|seven|members?)\s+(have\s+)?(signed|autographed)',
        r'(band\s+signed|fully\s+signed|all\s+members?\s+signed)',
        r'signed\s+by\s+all',
    ]
    solo_patterns = [
        r'signed\s+by\s+[a-z]+\s+[a-z]+',
        r'(vocalist|guitarist|bassist|drummer|frontman|singer|sole\s+member)\s+(signed|autographed)',
    ]
    if any(re.search(p, combined) for p in band_patterns):
        signed_by = "band"
    elif any(re.search(p, combined) for p in solo_patterns):
        signed_by = "solo"

    # ── Signature location ──
    sig_loc = "unknown"
    loc_patterns = [
        (r'signed\s+(on\s+the\s+)?cover|cover\s+(signed|autographed)|signed\s+cover', "cover"),
        (r'signed\s+insert|insert\s+(signed|autographed)|autographed\s+insert', "insert"),
        (r'signed\s+booklet|booklet\s+(signed|autographed)', "booklet"),
        (r'signed\s+sleeve|sleeve\s+(signed|autographed)', "sleeve"),
        (r'signed\s+on\s+(the\s+)?label|label\s+signed', "label"),
        (r'signed\s+litho|lithograph\s+signed|signed\s+lithograph', "lithograph"),
        (r'signed\s+poster|poster\s+signed', "poster"),
        (r'signed\s+(on\s+the\s+)?jacket|jacket\s+signed', "jacket"),
    ]
    for pattern, location in loc_patterns:
        if re.search(pattern, combined):
            sig_loc = location
            break

    return fmt, signed_by, sig_loc


# ─── Shopify JSON Scraper ─────────────────────────────────────────────────────

async def scrape_shopify(
    client: httpx.AsyncClient,
    collection_json_url: str,
    shop_name: str,
    base_url: str,
) -> list[Listing]:
    """Generic Shopify /products.json scraper — no browser needed."""
    listings = []
    page = 1
    while True:
        url = f"{collection_json_url}?limit=250&page={page}"
        try:
            resp = await client.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ERROR fetching {url}: {e}")
            break

        products = data.get("products", [])
        if not products:
            break

        for product in products:
            title = product.get("title", "")
            if not title:
                continue
            artist = product.get("vendor") or "Unknown"
            variants = product.get("variants") or []
            # Skip products where every variant is sold out
            if variants and not any(v.get("available", True) for v in variants):
                continue
            price_raw = variants[0].get("price", "") if variants else ""
            try:
                price = f"${float(price_raw):.2f}" if price_raw else None
            except ValueError:
                price = price_raw or None
            images = product.get("images") or []
            image_url = images[0].get("src") if images else None
            handle = product.get("handle", "")
            product_url = f"{base_url}/products/{handle}"
            body_html = product.get("body_html") or ""
            description = BeautifulSoup(body_html, "html.parser").get_text(
                separator=" ", strip=True
            )[:1000]
            fmt, signed_by, sig_loc = parse_signed_metadata(title, description)

            listings.append(Listing(
                shop=shop_name,
                artist=artist,
                title=title,
                format=fmt,
                signed_by=signed_by,
                signature_location=sig_loc,
                price=price,
                url=product_url,
                image_url=image_url,
                description=description or None,
            ))

        if len(products) < 250:
            break
        page += 1

    return listings


async def scrape_parkave(client: httpx.AsyncClient) -> list[Listing]:
    print("  → Park Ave CDs (Shopify JSON)...")
    listings = await scrape_shopify(
        client,
        "https://parkavecds.shop/collections/park-ave-cds-signed-exclusives/products.json",
        "Park Ave CDs",
        "https://parkavecds.shop",
    )
    print(f"  → Found {len(listings)} listings")
    return listings


# ─── 3hive ────────────────────────────────────────────────────────────────────

async def scrape_3hive(client: httpx.AsyncClient, page: Page) -> list[Listing]:
    """Try Shopify JSON first; fall back to HTML scraping."""
    print("  → 3hive...")
    try:
        resp = await client.get(
            "https://shop.3hive.com/collections/signed-vinyl/products.json?limit=250",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("products"):
                listings = await scrape_shopify(
                    client,
                    "https://shop.3hive.com/collections/signed-vinyl/products.json",
                    "3hive",
                    "https://shop.3hive.com",
                )
                print(f"  → Found {len(listings)} listings (Shopify JSON)")
                return listings
    except Exception:
        pass

    return await _scrape_3hive_html(page)


async def _scrape_3hive_html(page: Page) -> list[Listing]:
    BASE = "https://shop.3hive.com"
    listings = []
    seen: set[str] = set()
    page_num = 1

    while page_num <= 10:
        url = (
            f"{BASE}/shop/signed-vinyl/137"
            f"?page={page_num}&limit=30&sort_by=created_date&sort_order=desc"
        )
        print(f"  → 3hive HTML page {page_num}...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  ERROR loading 3hive page {page_num}: {e}")
            break

        soup = BeautifulSoup(await page.content(), "html.parser")
        cards = (
            soup.select(".product-item, .product-card, .grid-item, [class*='product']")
            or soup.select("article, .item")
        )

        page_listings = []
        for card in cards:
            title_el = card.select_one(
                "h2, h3, h4, .product-title, .product-name, [class*='title']"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            price_el = card.select_one(".price, [class*='price']")
            price = price_el.get_text(strip=True) if price_el else None

            img_el = card.select_one("img")
            image_url = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

            link_el = card.select_one("a[href]")
            product_url = link_el["href"] if link_el else None
            if product_url and not product_url.startswith("http"):
                product_url = BASE + product_url
            if not product_url:
                continue

            fmt, signed_by, sig_loc = parse_signed_metadata(title, "")
            lst = Listing(
                shop="3hive",
                artist="Unknown",
                title=title,
                format=fmt,
                signed_by=signed_by,
                signature_location=sig_loc,
                price=price,
                url=product_url,
                image_url=image_url,
                description=None,
            )
            if lst.hash not in seen:
                seen.add(lst.hash)
                page_listings.append(lst)

        listings.extend(page_listings)
        print(f"  → Found {len(page_listings)} listings")

        if len(page_listings) < 10:
            break
        page_num += 1

    return listings


# ─── SG Record Shop ───────────────────────────────────────────────────────────

async def scrape_sgrecordshop(page: Page) -> list[Listing]:
    """Paginated HTML catalog sorted newest first."""
    BASE = "https://www.sgrecordshop.com"
    listings = []
    seen: set[str] = set()
    page_num = 1

    while page_num <= 20:
        url = f"{BASE}/c/2865/artist-signed-vinyl?&so=9&page={page_num}&af=-10"
        print(f"  → SG Record Shop page {page_num}...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  ERROR loading SG Record Shop page {page_num}: {e}")
            break

        soup = BeautifulSoup(await page.content(), "html.parser")

        cards = soup.select(
            ".product-tile, .product-item, .catalog-item, "
            "[class*='product-cell'], [data-product-id], .prod-item"
        )
        if not cards:
            cards = soup.select(".product")

        page_listings = []
        for card in cards:
            title_el = card.select_one(
                ".product-name, .item-name, h3, h4, [class*='name'], [class*='title']"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            artist_el = card.select_one(".product-artist, .artist, [class*='artist']")
            artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

            price_el = card.select_one(
                ".price, [class*='price'], .sale-price, .our-price"
            )
            price = re.sub(r"\s+", " ", price_el.get_text(strip=True)).strip() if price_el else None

            img_el = card.select_one("img")
            image_url = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

            link_el = card.select_one("a[href]")
            product_url = link_el["href"] if link_el else None
            if product_url and not product_url.startswith("http"):
                product_url = BASE + product_url
            if not product_url:
                continue

            fmt, signed_by, sig_loc = parse_signed_metadata(title, "")
            lst = Listing(
                shop="SG Record Shop",
                artist=artist,
                title=title,
                format=fmt,
                signed_by=signed_by,
                signature_location=sig_loc,
                price=price,
                url=product_url,
                image_url=image_url,
                description=None,
            )
            if lst.hash not in seen:
                seen.add(lst.hash)
                page_listings.append(lst)

        listings.extend(page_listings)
        print(f"  → Found {len(page_listings)} listings on page {page_num}")

        if len(page_listings) == 0:
            break
        page_num += 1

    return listings


# ─── Banquet Records ──────────────────────────────────────────────────────────

async def scrape_banquet(page: Page) -> list[Listing]:
    """Search results for 'signed'; post-filter to ensure signed items only."""
    BASE = "https://www.banquetrecords.com"
    url = f"{BASE}/search?q=signed&t=signed"
    listings = []
    seen: set[str] = set()

    print("  → Banquet Records...")
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  ERROR loading Banquet Records: {e}")
        return listings

    prev_height = 0
    for _ in range(20):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1200)
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height

    soup = BeautifulSoup(await page.content(), "html.parser")
    cards = soup.select(
        ".product, .product-item, .search-result, "
        "[class*='product-card'], [class*='result-item']"
    )
    if not cards:
        cards = soup.select("article, li.item")

    for card in cards:
        title_el = card.select_one(
            "h2, h3, h4, .product-title, .product-name, [class*='title'], [class*='name']"
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        desc_el = card.select_one(".description, .product-description, p, [class*='desc']")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # Must mention "signed" somewhere to stay in results
        if "signed" not in title.lower() and "signed" not in description.lower():
            continue

        artist_el = card.select_one(".artist, .product-artist, [class*='artist']")
        artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

        price_el = card.select_one(".price, [class*='price']")
        price = price_el.get_text(strip=True) if price_el else None

        img_el = card.select_one("img")
        image_url = None
        if img_el:
            image_url = img_el.get("src") or img_el.get("data-src")
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

        link_el = card.select_one("a[href]")
        product_url = link_el["href"] if link_el else None
        if product_url and not product_url.startswith("http"):
            product_url = BASE + product_url
        if not product_url:
            continue

        fmt, signed_by, sig_loc = parse_signed_metadata(title, description)
        lst = Listing(
            shop="Banquet Records",
            artist=artist,
            title=title,
            format=fmt,
            signed_by=signed_by,
            signature_location=sig_loc,
            price=price,
            url=product_url,
            image_url=image_url,
            description=description[:500] if description else None,
        )
        if lst.hash not in seen:
            seen.add(lst.hash)
            listings.append(lst)

    print(f"  → Found {len(listings)} signed listings")
    return listings


# ─── Shopify JSON Scrapers ────────────────────────────────────────────────────

async def scrape_nailcityrecord(client: httpx.AsyncClient) -> list[Listing]:
    print("  → Nail City Record (Shopify JSON)...")
    listings = await scrape_shopify(
        client,
        "https://nailcityrecord.com/collections/autographed-signed-editions/products.json",
        "Nail City Record",
        "https://nailcityrecord.com",
    )
    print(f"  → Found {len(listings)} listings")
    return listings


async def scrape_darksiderecords(client: httpx.AsyncClient) -> list[Listing]:
    print("  → Darkside Records (Shopify JSON)...")
    listings = await scrape_shopify(
        client,
        "https://shop.darksiderecords.com/collections/autographed-items/products.json",
        "Darkside Records",
        "https://shop.darksiderecords.com",
    )
    print(f"  → Found {len(listings)} listings")
    return listings


async def scrape_assai(client: httpx.AsyncClient) -> list[Listing]:
    print("  → Assai Records (Shopify JSON)...")
    listings = await scrape_shopify(
        client,
        "https://assai.co.uk/collections/signed-vinyl/products.json",
        "Assai Records",
        "https://assai.co.uk",
    )
    print(f"  → Found {len(listings)} listings")
    return listings


async def scrape_musicrecordshop(client: httpx.AsyncClient) -> list[Listing]:
    print("  → Music Record Shop (Shopify JSON)...")
    listings = await scrape_shopify(
        client,
        "https://musicrecordshop.com/collections/signed-vinyl/products.json",
        "Music Record Shop",
        "https://musicrecordshop.com",
    )
    print(f"  → Found {len(listings)} listings")
    return listings


async def scrape_rarelimiteds(client: httpx.AsyncClient) -> list[Listing]:
    print("  → Rare Limiteds (Shopify JSON)...")
    listings = await scrape_shopify(
        client,
        "https://rarelimiteds.com/collections/autographed/products.json",
        "Rare Limiteds",
        "https://rarelimiteds.com",
    )
    print(f"  → Found {len(listings)} listings")
    return listings


async def scrape_cleorecs(client: httpx.AsyncClient) -> list[Listing]:
    print("  → Cleo Recs (Shopify JSON)...")
    listings = await scrape_shopify(
        client,
        "https://cleorecs.com/collections/signed-items/products.json",
        "Cleo Recs",
        "https://cleorecs.com",
    )
    print(f"  → Found {len(listings)} listings")
    return listings


# ─── Zia Records ──────────────────────────────────────────────────────────────

async def scrape_ziarecords(page: Page) -> list[Listing]:
    """Paginated HTML catalog sorted newest first."""
    BASE = "https://www.ziarecords.com"
    listings = []
    seen: set[str] = set()
    page_num = 1

    while page_num <= 20:
        url = f"{BASE}/c/539/signed-albums?&so=9&page={page_num}"
        print(f"  → Zia Records page {page_num}...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  ERROR loading Zia Records page {page_num}: {e}")
            break

        soup = BeautifulSoup(await page.content(), "html.parser")
        cards = soup.select(
            ".product-tile, .product-item, .catalog-item, "
            "[class*='product-cell'], [data-product-id], .prod-item"
        )
        if not cards:
            cards = soup.select(".product")

        page_listings = []
        for card in cards:
            title_el = card.select_one(
                ".product-name, .item-name, h3, h4, [class*='name'], [class*='title']"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            artist_el = card.select_one(".product-artist, .artist, [class*='artist']")
            artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

            price_el = card.select_one(".price, [class*='price'], .sale-price, .our-price")
            price = re.sub(r"\s+", " ", price_el.get_text(strip=True)).strip() if price_el else None

            img_el = card.select_one("img")
            image_url = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

            link_el = card.select_one("a[href]")
            product_url = link_el["href"] if link_el else None
            if product_url and not product_url.startswith("http"):
                product_url = BASE + product_url
            if not product_url:
                continue

            fmt, signed_by, sig_loc = parse_signed_metadata(title, "")
            lst = Listing(
                shop="Zia Records",
                artist=artist,
                title=title,
                format=fmt,
                signed_by=signed_by,
                signature_location=sig_loc,
                price=price,
                url=product_url,
                image_url=image_url,
                description=None,
            )
            if lst.hash not in seen:
                seen.add(lst.hash)
                page_listings.append(lst)

        listings.extend(page_listings)
        print(f"  → Found {len(page_listings)} listings on page {page_num}")

        if len(page_listings) == 0:
            break
        page_num += 1

    return listings


# ─── Rare Vinyl ───────────────────────────────────────────────────────────────

async def scrape_rarevinyl(page: Page) -> list[Listing]:
    BASE = "https://us.rarevinyl.com"
    listings = []
    seen: set[str] = set()
    page_num = 1

    while page_num <= 20:
        url = f"{BASE}/collections/autographs?tab=products&page={page_num}"
        print(f"  → Rare Vinyl page {page_num}...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  ERROR loading Rare Vinyl page {page_num}: {e}")
            break

        soup = BeautifulSoup(await page.content(), "html.parser")
        cards = soup.select(
            ".product-item, .product-card, .grid-item, "
            "[class*='product'], article.product"
        )
        if not cards:
            cards = soup.select("li.item, .result-item")

        page_listings = []
        for card in cards:
            title_el = card.select_one(
                "h2, h3, h4, .product-title, .product-name, [class*='title'], [class*='name']"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            artist_el = card.select_one(".artist, .product-artist, [class*='artist']")
            artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

            price_el = card.select_one(".price, [class*='price']")
            price = price_el.get_text(strip=True) if price_el else None

            img_el = card.select_one("img")
            image_url = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

            link_el = card.select_one("a[href]")
            product_url = link_el["href"] if link_el else None
            if product_url and not product_url.startswith("http"):
                product_url = BASE + product_url
            if not product_url:
                continue

            fmt, signed_by, sig_loc = parse_signed_metadata(title, "")
            lst = Listing(
                shop="Rare Vinyl",
                artist=artist,
                title=title,
                format=fmt,
                signed_by=signed_by,
                signature_location=sig_loc,
                price=price,
                url=product_url,
                image_url=image_url,
                description=None,
            )
            if lst.hash not in seen:
                seen.add(lst.hash)
                page_listings.append(lst)

        listings.extend(page_listings)
        print(f"  → Found {len(page_listings)} listings on page {page_num}")

        if len(page_listings) == 0:
            break
        page_num += 1

    return listings


# ─── Rough Trade ──────────────────────────────────────────────────────────────

async def scrape_roughtrade(page: Page) -> list[Listing]:
    BASE = "https://www.roughtrade.com"
    url = f"{BASE}/en-us/search?q=signed&sortBy=newest_released&signed=true"
    listings = []
    seen: set[str] = set()

    print("  → Rough Trade...")
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  ERROR loading Rough Trade: {e}")
        return listings

    prev_height = 0
    for _ in range(20):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1200)
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height

    soup = BeautifulSoup(await page.content(), "html.parser")
    cards = soup.select(
        ".product, .product-item, .search-result, "
        "[class*='product-card'], [class*='result-item']"
    )
    if not cards:
        cards = soup.select("article, li.item")

    for card in cards:
        title_el = card.select_one(
            "h2, h3, h4, .product-title, .product-name, [class*='title'], [class*='name']"
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        artist_el = card.select_one(".artist, .product-artist, [class*='artist']")
        artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

        desc_el = card.select_one(".description, p, [class*='desc']")
        description = desc_el.get_text(strip=True) if desc_el else ""

        price_el = card.select_one(".price, [class*='price']")
        price = price_el.get_text(strip=True) if price_el else None

        img_el = card.select_one("img")
        image_url = None
        if img_el:
            image_url = img_el.get("src") or img_el.get("data-src")
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

        link_el = card.select_one("a[href]")
        product_url = link_el["href"] if link_el else None
        if product_url and not product_url.startswith("http"):
            product_url = BASE + product_url
        if not product_url:
            continue

        fmt, signed_by, sig_loc = parse_signed_metadata(title, description)
        lst = Listing(
            shop="Rough Trade",
            artist=artist,
            title=title,
            format=fmt,
            signed_by=signed_by,
            signature_location=sig_loc,
            price=price,
            url=product_url,
            image_url=image_url,
            description=description[:500] if description else None,
        )
        if lst.hash not in seen:
            seen.add(lst.hash)
            listings.append(lst)

    print(f"  → Found {len(listings)} listings")
    return listings


# ─── Looney Tunes Long Island ─────────────────────────────────────────────────

async def scrape_looneytunes(page: Page) -> list[Listing]:
    BASE = "https://www.looneytuneslongisland.com"
    listings = []
    seen: set[str] = set()
    page_num = 1

    while page_num <= 20:
        url = f"{BASE}/autographeditems" if page_num == 1 else f"{BASE}/autographeditems?page={page_num}"
        print(f"  → Looney Tunes Long Island page {page_num}...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  ERROR loading Looney Tunes page {page_num}: {e}")
            break

        soup = BeautifulSoup(await page.content(), "html.parser")
        cards = soup.select(
            ".product-item, .product-card, .grid-item, "
            "[class*='product'], .item"
        )
        if not cards:
            cards = soup.select("article, li.product")

        page_listings = []
        for card in cards:
            title_el = card.select_one(
                "h2, h3, h4, .product-title, .product-name, [class*='title'], [class*='name']"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            artist_el = card.select_one(".artist, .product-artist, [class*='artist']")
            artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

            price_el = card.select_one(".price, [class*='price']")
            price = price_el.get_text(strip=True) if price_el else None

            img_el = card.select_one("img")
            image_url = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

            link_el = card.select_one("a[href]")
            product_url = link_el["href"] if link_el else None
            if product_url and not product_url.startswith("http"):
                product_url = BASE + product_url
            if not product_url:
                continue

            fmt, signed_by, sig_loc = parse_signed_metadata(title, "")
            lst = Listing(
                shop="Looney Tunes Long Island",
                artist=artist,
                title=title,
                format=fmt,
                signed_by=signed_by,
                signature_location=sig_loc,
                price=price,
                url=product_url,
                image_url=image_url,
                description=None,
            )
            if lst.hash not in seen:
                seen.add(lst.hash)
                page_listings.append(lst)

        listings.extend(page_listings)
        print(f"  → Found {len(page_listings)} listings on page {page_num}")

        if len(page_listings) == 0:
            break
        page_num += 1

    return listings


# ─── Fingerprints Music ───────────────────────────────────────────────────────

async def scrape_fingerprints(page: Page) -> list[Listing]:
    BASE = "https://shop.fingerprintsmusic.com"
    listings = []
    seen: set[str] = set()
    page_num = 1

    while page_num <= 20:
        url = (
            f"{BASE}/Search?terms=autographed&availability=purchase&condition=any"
            f"&release_date_start=&release_date_end=&page={page_num}"
        )
        print(f"  → Fingerprints Music page {page_num}...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  ERROR loading Fingerprints Music page {page_num}: {e}")
            break

        soup = BeautifulSoup(await page.content(), "html.parser")
        cards = soup.select(
            ".product-item, .product-card, .grid-item, .search-result, "
            "[class*='product'], [class*='result']"
        )
        if not cards:
            cards = soup.select("article, li.item")

        page_listings = []
        for card in cards:
            title_el = card.select_one(
                "h2, h3, h4, .product-title, .product-name, [class*='title'], [class*='name']"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            artist_el = card.select_one(".artist, .product-artist, [class*='artist']")
            artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

            price_el = card.select_one(".price, [class*='price']")
            price = price_el.get_text(strip=True) if price_el else None

            img_el = card.select_one("img")
            image_url = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

            link_el = card.select_one("a[href]")
            product_url = link_el["href"] if link_el else None
            if product_url and not product_url.startswith("http"):
                product_url = BASE + product_url
            if not product_url:
                continue

            fmt, signed_by, sig_loc = parse_signed_metadata(title, "")
            lst = Listing(
                shop="Fingerprints Music",
                artist=artist,
                title=title,
                format=fmt,
                signed_by=signed_by,
                signature_location=sig_loc,
                price=price,
                url=product_url,
                image_url=image_url,
                description=None,
            )
            if lst.hash not in seen:
                seen.add(lst.hash)
                page_listings.append(lst)

        listings.extend(page_listings)
        print(f"  → Found {len(page_listings)} listings on page {page_num}")

        if len(page_listings) == 0:
            break
        page_num += 1

    return listings


# ─── Plaid Room Records ───────────────────────────────────────────────────────

async def scrape_plaidroomrecords(page: Page) -> list[Listing]:
    BASE = "https://www.plaidroomrecords.com"
    listings = []
    seen: set[str] = set()

    print("  → Plaid Room Records...")
    url = (
        f"{BASE}/search?sort_by=created-descending&q=signed"
        "&type=product&filter.v.availability=1"
    )
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  ERROR loading Plaid Room Records: {e}")
        return listings

    prev_height = 0
    for _ in range(20):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1200)
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height

    soup = BeautifulSoup(await page.content(), "html.parser")
    cards = soup.select(
        ".product-item, .product-card, .grid-item, "
        "[class*='product'], .search-result-item"
    )
    if not cards:
        cards = soup.select("article, li.item")

    for card in cards:
        title_el = card.select_one(
            "h2, h3, h4, .product-title, .product-name, [class*='title'], [class*='name']"
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        artist_el = card.select_one(".artist, .product-artist, [class*='artist'], .vendor")
        artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

        price_el = card.select_one(".price, [class*='price']")
        price = price_el.get_text(strip=True) if price_el else None

        img_el = card.select_one("img")
        image_url = None
        if img_el:
            image_url = img_el.get("src") or img_el.get("data-src")
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

        link_el = card.select_one("a[href]")
        product_url = link_el["href"] if link_el else None
        if product_url and not product_url.startswith("http"):
            product_url = BASE + product_url
        if not product_url:
            continue

        fmt, signed_by, sig_loc = parse_signed_metadata(title, "")
        lst = Listing(
            shop="Plaid Room Records",
            artist=artist,
            title=title,
            format=fmt,
            signed_by=signed_by,
            signature_location=sig_loc,
            price=price,
            url=product_url,
            image_url=image_url,
            description=None,
        )
        if lst.hash not in seen:
            seen.add(lst.hash)
            listings.append(lst)

    print(f"  → Found {len(listings)} listings")
    return listings


# ─── Seasick Birmingham ───────────────────────────────────────────────────────

async def scrape_seasick(page: Page) -> list[Listing]:
    BASE = "https://seasickbham.com"
    listings = []
    seen: set[str] = set()

    print("  → Seasick Birmingham...")
    url = f"{BASE}/search?type=product&q=autographed"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  ERROR loading Seasick Birmingham: {e}")
        return listings

    prev_height = 0
    for _ in range(20):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1200)
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height

    soup = BeautifulSoup(await page.content(), "html.parser")
    cards = soup.select(
        ".product-item, .product-card, .grid-item, "
        "[class*='product'], .search-result-item"
    )
    if not cards:
        cards = soup.select("article, li.item")

    for card in cards:
        title_el = card.select_one(
            "h2, h3, h4, .product-title, .product-name, [class*='title'], [class*='name']"
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        desc_el = card.select_one(".description, p, [class*='desc']")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # Post-filter: must mention autograph/signed
        combined_check = f"{title} {description}".lower()
        if "autograph" not in combined_check and "signed" not in combined_check:
            continue

        artist_el = card.select_one(".artist, .product-artist, [class*='artist'], .vendor")
        artist = artist_el.get_text(strip=True) if artist_el else "Unknown"

        price_el = card.select_one(".price, [class*='price']")
        price = price_el.get_text(strip=True) if price_el else None

        img_el = card.select_one("img")
        image_url = None
        if img_el:
            image_url = img_el.get("src") or img_el.get("data-src")
            if image_url and image_url.startswith("//"):
                image_url = "https:" + image_url

        link_el = card.select_one("a[href]")
        product_url = link_el["href"] if link_el else None
        if product_url and not product_url.startswith("http"):
            product_url = BASE + product_url
        if not product_url:
            continue

        fmt, signed_by, sig_loc = parse_signed_metadata(title, description)
        lst = Listing(
            shop="Seasick Birmingham",
            artist=artist,
            title=title,
            format=fmt,
            signed_by=signed_by,
            signature_location=sig_loc,
            price=price,
            url=product_url,
            image_url=image_url,
            description=description[:500] if description else None,
        )
        if lst.hash not in seen:
            seen.add(lst.hash)
            listings.append(lst)

    print(f"  → Found {len(listings)} listings")
    return listings


# ─── Config ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    recipients_raw = os.environ.get("EMAIL_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    return {
        "email": {
            "enabled": os.environ.get("EMAIL_ENABLED", "").lower() in ("1", "true", "yes"),
            "smtp_server": os.environ.get("EMAIL_SMTP_SERVER", "smtp.gmail.com"),
            "smtp_port": int(os.environ.get("EMAIL_SMTP_PORT", "587")),
            "sender": os.environ.get("EMAIL_SENDER", ""),
            "password": os.environ.get("EMAIL_PASSWORD", ""),
            "recipients": recipients,
        }
    }


# ─── Email ────────────────────────────────────────────────────────────────────

def _format_badge_email(fmt: str) -> str:
    return _render_format_badge_email(fmt)


def _shop_block_html(shop: str, listings: list[Listing]) -> str:
    view_models = [to_email_listing_view_model(listing) for listing in listings]
    return _render_shop_block_html(shop, view_models)


def build_email_html(new_listings: list[Listing]) -> str:
    view_models = [to_email_listing_view_model(listing) for listing in new_listings]
    return _render_build_email_html(view_models)


def send_email(new_listings: list[Listing], config: dict):
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled"):
        return

    sender = email_cfg["sender"]
    password = email_cfg["password"]
    recipients = email_cfg["recipients"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"New Signed Records — {len(new_listings)} listing"
        f"{'s' if len(new_listings) != 1 else ''} — {datetime.now().strftime('%b %d')}"
    )
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    by_shop: dict[str, list[Listing]] = {}
    for lst in new_listings:
        by_shop.setdefault(lst.shop, []).append(lst)
    plain_lines = [f"{len(new_listings)} new signed listing(s):\n"]
    for shop in sorted(by_shop):
        plain_lines.append(f"{shop}")
        for lst in by_shop[shop]:
            plain_lines.append(f"  {lst.title} ({lst.format}){' — ' + lst.price if lst.price else ''}")
            plain_lines.append(f"  {lst.url}")
        plain_lines.append("")

    msg.attach(MIMEText("\n".join(plain_lines), "plain"))
    msg.attach(MIMEText(build_email_html(new_listings), "html"))

    try:
        with smtplib.SMTP(
            email_cfg.get("smtp_server", "smtp.gmail.com"),
            email_cfg.get("smtp_port", 587),
        ) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
        print(f"Email sent to {', '.join(recipients)}")
    except Exception as e:
        print(f"Email failed: {e}")


# ─── Main Orchestrator ────────────────────────────────────────────────────────

async def run_scraper():
    run_time = datetime.now()
    print(f"{'='*60}")
    print(f"  Autograph Notifier — {run_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    conn = init_db()
    all_listings: list[Listing] = []

    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    async with httpx.AsyncClient(
        headers={"User-Agent": ua}, follow_redirects=True
    ) as client:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=ua)

            sg_page = await context.new_page()
            banquet_page = await context.new_page()
            hive_page = await context.new_page()
            zia_page = await context.new_page()
            rarevinyl_page = await context.new_page()
            roughtrade_page = await context.new_page()
            looneytunes_page = await context.new_page()
            fingerprints_page = await context.new_page()
            plaidroom_page = await context.new_page()
            seasick_page = await context.new_page()

            print("Scraping shops...\n")
            results = await asyncio.gather(
                scrape_parkave(client),
                scrape_3hive(client, hive_page),
                scrape_sgrecordshop(sg_page),
                scrape_banquet(banquet_page),
                scrape_nailcityrecord(client),
                scrape_darksiderecords(client),
                scrape_assai(client),
                scrape_musicrecordshop(client),
                scrape_rarelimiteds(client),
                scrape_cleorecs(client),
                scrape_ziarecords(zia_page),
                scrape_rarevinyl(rarevinyl_page),
                scrape_roughtrade(roughtrade_page),
                scrape_looneytunes(looneytunes_page),
                scrape_fingerprints(fingerprints_page),
                scrape_plaidroomrecords(plaidroom_page),
                scrape_seasick(seasick_page),
                return_exceptions=True,
            )

            await browser.close()

    # Collect listings and track which shops scraped successfully (returned ≥1 result)
    successful_shops: set[str] = set()
    for r in results:
        if isinstance(r, Exception):
            print(f"  Scraper error: {r}")
        elif isinstance(r, list):
            all_listings.extend(r)
            for lst in r:
                successful_shops.add(lst.shop)

    all_listings = deduplicate_listings(all_listings)
    print(f"\nTotal scraped: {len(all_listings)} listings")

    print("\nComparing with database to detect new listings...")
    new_listings = upsert_listings(conn, all_listings, run_time)

    archived_count = archive_stale_listings(conn, list(successful_shops), run_time)
    if archived_count:
        print(f"Archived {archived_count} listing(s) no longer found in shops.")

    config = load_config()
    if new_listings:
        print(f"\nNew listings ({len(new_listings)}):")
        for lst in new_listings:
            price_str = f" — {lst.price}" if lst.price else ""
            print(f"  [{lst.shop}] {lst.title} ({lst.format}){price_str}")
        send_email(new_listings, config)
    else:
        print("No new listings since last run.")

    print(f"\n{'='*60}")
    print(f"  RESULTS: {len(all_listings)} total, {len(new_listings)} NEW, {archived_count} ARCHIVED")
    print(f"{'='*60}\n")

    conn.close()
    return new_listings


if __name__ == "__main__":
    asyncio.run(run_scraper())
