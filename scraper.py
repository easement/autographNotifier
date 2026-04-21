"""
Autograph Notifier
Scrapes signed records/CDs from online shops, detects new listings,
stores results in Supabase/PostgreSQL, sends email notifications.

Requires: pip install playwright beautifulsoup4 psycopg[binary] httpx python-dotenv
           playwright install chromium
"""

import asyncio
import hashlib
import html as html_module
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
            last_seen           TIMESTAMPTZ
        )
    """)
    conn.commit()
    return conn


def upsert_listings(conn, listings: list[Listing]) -> list[Listing]:
    """Insert new listings, update last_seen for existing ones. Returns NEW listings only."""
    now = datetime.now()
    new_listings = []
    for lst in listings:
        existing = conn.execute(
            "SELECT hash FROM listings WHERE hash = %s", (lst.hash,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE listings SET last_seen = %s WHERE hash = %s", (now, lst.hash)
            )
        else:
            conn.execute(
                """INSERT INTO listings
                    (hash, shop, artist, title, format, signed_by, signature_location,
                     price, url, image_url, description, first_seen, last_seen)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (lst.hash, lst.shop, lst.artist, lst.title, lst.format, lst.signed_by,
                 lst.signature_location, lst.price, lst.url, lst.image_url,
                 lst.description, now, now),
            )
            new_listings.append(lst)
    conn.commit()
    return new_listings


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

# ─── Par Avion design tokens (email-safe, mirroring the web design system) ────
#   paper      #F2E8D5   cream background
#   paper-2    #EADFC7   alt surface
#   surface    #FAF3E1   input / highlight surface
#   ink        #121212   primary text
#   ink-3      #6B6358   muted text
#   red        #B91C1C   airmail red — LP badges, CTAs, dividers
#   blue       #1E3A8A   airmail blue — CD badges only
#   border     #C9B994   thead underline
#   border-sft #DDD0B3   row dividers
#
#   Display font: Oswald → fallback "Arial Narrow", Impact, Helvetica, sans-serif
#   Body font:    Source Serif 4 → fallback Georgia, "Times New Roman", serif
#   Mono font:    JetBrains Mono → fallback "Courier New", Courier, monospace

_FONT_DISPLAY = "'Oswald','Arial Narrow',Impact,Helvetica,sans-serif"
_FONT_BODY = "'Source Serif 4',Georgia,'Times New Roman',serif"
_FONT_MONO = "'JetBrains Mono','Courier New',Courier,monospace"

# Red for LP (and any unknown/vinyl variant), blue for CD only.
_CD_BADGE_COLOR = "#1E3A8A"
_DEFAULT_BADGE_COLOR = "#B91C1C"


def _format_badge_email(fmt: str) -> str:
    if fmt == "unknown" or not fmt:
        return ""
    color = _CD_BADGE_COLOR if fmt == "CD" else _DEFAULT_BADGE_COLOR
    return (
        f'<span style="display:inline-block;background:{color};color:#F2E8D5;'
        f"font-family:{_FONT_DISPLAY};font-size:11px;font-weight:600;"
        f'letter-spacing:2px;text-transform:uppercase;padding:3px 8px;'
        f'border-radius:0;margin-left:8px;">{html_module.escape(fmt)}</span>'
    )


def _shop_block_html(shop: str, listings: list[Listing]) -> str:
    rows = []
    for i, lst in enumerate(listings):
        is_last = i == len(listings) - 1
        row_border = "" if is_last else "border-bottom:1px solid #DDD0B3;"
        badge = _format_badge_email(lst.format)

        meta_parts = []
        if lst.signed_by != "unknown":
            meta_parts.append(f"signed by: {lst.signed_by}")
        if lst.signature_location != "unknown":
            meta_parts.append(f"location: {lst.signature_location}")
        meta_str = "  ·  ".join(meta_parts)
        meta_html = (
            f'<div style="font-family:{_FONT_MONO};font-size:12px;line-height:18px;'
            f'color:#6B6358;margin-top:4px;">{html_module.escape(meta_str)}</div>'
            if meta_str
            else ""
        )

        alt_text = (
            f"{lst.title} by {lst.artist}"
            if lst.artist and lst.artist.lower() != "unknown"
            else lst.title
        )
        img_cell = (
            f'<td width="64" style="padding:14px 12px 14px 0;vertical-align:middle;width:64px;">'
            f'<img src="{html_module.escape(lst.image_url)}" width="52" height="52" '
            f'alt="{html_module.escape(alt_text)}" '
            f'style="display:block;border:1px solid #121212;border-radius:0;'
            f'width:52px;height:52px;object-fit:cover;"></td>'
            if lst.image_url
            else (
                '<td width="64" style="padding:14px 12px 14px 0;vertical-align:middle;width:64px;">'
                '<div role="presentation" aria-hidden="true" '
                'style="width:52px;height:52px;background:#EADFC7;border:1px solid #C9B994;"></div>'
                '</td>'
            )
        )

        # Bulletproof Buy button — VML for Outlook + HTML for everyone else.
        buy_block = ""
        if lst.url:
            buy_href = html_module.escape(lst.url)
            buy_block = f"""
                <!--[if mso]>
                <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml"
                  xmlns:w="urn:schemas-microsoft-com:office:word"
                  href="{buy_href}"
                  style="height:30px;v-text-anchor:middle;width:82px;"
                  arcsize="0%" strokecolor="#B91C1C" strokeweight="1.5pt"
                  fillcolor="#F2E8D5">
                  <w:anchorlock/>
                  <center style="color:#B91C1C;font-family:Arial,sans-serif;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;">Buy now</center>
                </v:roundrect>
                <![endif]-->
                <!--[if !mso]><!-->
                <a href="{buy_href}"
                   style="display:inline-block;font-family:{_FONT_DISPLAY};
                   font-size:12px;font-weight:600;letter-spacing:2px;
                   text-transform:uppercase;color:#B91C1C;text-decoration:none;
                   border:1.5px solid #B91C1C;padding:6px 14px;border-radius:0;
                   background-color:#F2E8D5;mso-hide:all;">Buy now</a>
                <!--<![endif]-->"""

        price_html = (
            f'<div style="font-family:{_FONT_DISPLAY};font-size:15px;font-weight:600;'
            f'color:#121212;letter-spacing:-0.01em;margin-bottom:6px;'
            f'white-space:nowrap;">{html_module.escape(lst.price)}</div>'
            if lst.price
            else ""
        )

        rows.append(f"""
          <tr>
            {img_cell}
            <td style="padding:14px 12px;vertical-align:middle;{row_border}">
              <div style="font-family:{_FONT_BODY};font-size:16px;line-height:22px;
                   font-weight:400;color:#121212;">{html_module.escape(lst.title)}{badge}</div>
              <div style="font-family:{_FONT_MONO};font-size:13px;line-height:19px;
                   color:#6B6358;margin-top:4px;letter-spacing:0.02em;">{html_module.escape(lst.artist)}</div>
              {meta_html}
            </td>
            <td style="padding:14px 0 14px 12px;vertical-align:middle;text-align:right;
                white-space:nowrap;{row_border}">
              {price_html}
              {buy_block}
            </td>
          </tr>""")

    count_label = f"{len(listings)} listing{'s' if len(listings) != 1 else ''}"
    return f"""
      <tr>
        <td style="padding:32px 24px 0 24px;">
          <h2 style="mso-line-height-rule:exactly;margin:0;padding-bottom:10px;
              border-bottom:1.5px solid #B91C1C;font-family:{_FONT_DISPLAY};
              font-size:22px;line-height:26px;letter-spacing:2px;font-weight:600;
              color:#121212;text-transform:uppercase;">{html_module.escape(shop)}</h2>
          <div style="font-family:{_FONT_MONO};font-size:12px;line-height:18px;
               letter-spacing:2px;color:#6B6358;text-transform:uppercase;
               margin-top:6px;">{count_label}</div>
          <table role="presentation" cellpadding="0" cellspacing="0" border="0"
                 width="100%" style="width:100%;border-collapse:collapse;margin-top:4px;">
            {"".join(rows)}
          </table>
        </td>
      </tr>"""


def build_email_html(new_listings: list[Listing]) -> str:
    by_shop: dict[str, list[Listing]] = {}
    for lst in new_listings:
        by_shop.setdefault(lst.shop, []).append(lst)

    shops_html = "".join(
        _shop_block_html(shop, by_shop[shop]) for shop in sorted(by_shop)
    )
    now = datetime.now()
    count = len(new_listings)
    count_word = f"{count} new listing{'s' if count != 1 else ''}"
    preview = (
        f"{count_word} across {len(by_shop)} shop"
        f"{'s' if len(by_shop) != 1 else ''} — scanned "
        f"{now.strftime('%b %d, %I:%M %p')}."
    )

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<title>Dispatches — Autograph Notifier</title>
<!--[if mso]>
<noscript><xml><o:OfficeDocumentSettings>
  <o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings></xml></noscript>
<![endif]-->
<style type="text/css">
  body, table, td, a {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  table, td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; }}
  img {{ -ms-interpolation-mode:bicubic; border:0; display:block; outline:none; text-decoration:none; }}
  body {{ margin:0 !important; padding:0 !important; width:100% !important; background-color:#F2E8D5; }}
  a[x-apple-data-detectors] {{ color:inherit !important; text-decoration:none !important; }}
  u + #body a {{ color:inherit; text-decoration:none; }}
  @media screen and (max-width:600px) {{
    .email-container {{ width:100% !important; max-width:100% !important; }}
    .mobile-pad {{ padding-left:20px !important; padding-right:20px !important; }}
    .mobile-title {{ font-size:16px !important; line-height:22px !important; }}
    .mobile-meta {{ font-size:14px !important; line-height:20px !important; }}
    .mobile-h1   {{ font-size:26px !important; line-height:30px !important; }}
    .mobile-h2   {{ font-size:20px !important; line-height:24px !important; }}
  }}
</style>
</head>
<body id="body" style="margin:0;padding:0;background-color:#F2E8D5;">

<span style="display:none;max-height:0;overflow:hidden;mso-hide:all;
     font-size:1px;color:#F2E8D5;line-height:1px;opacity:0;">
  {html_module.escape(preview)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
</span>

<table role="presentation" cellpadding="0" cellspacing="0" border="0"
       width="100%" style="background-color:#F2E8D5;">
  <tr>
    <td align="center" style="padding:24px 12px;">

      <table role="presentation" class="email-container" cellpadding="0" cellspacing="0"
             border="0" width="600"
             style="max-width:600px;width:100%;background-color:#F2E8D5;
                    border:1px solid #121212;">

        <tr>
          <td class="mobile-pad" style="padding:28px 24px 18px 24px;border-bottom:1px solid #121212;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td style="vertical-align:middle;">
                  <h1 class="mobile-h1" style="mso-line-height-rule:exactly;margin:0;
                      font-family:{_FONT_DISPLAY};font-size:28px;line-height:32px;
                      font-weight:600;letter-spacing:4px;text-transform:uppercase;
                      color:#121212;">
                    Autograph&nbsp;<span style="color:#B91C1C;">Notifier</span>
                  </h1>
                  <div style="font-family:{_FONT_MONO};font-size:11px;line-height:16px;
                       letter-spacing:2px;text-transform:uppercase;color:#6B6358;
                       margin-top:8px;">Signed &middot; Sealed &middot; Delivered</div>
                </td>
                <td align="right" style="vertical-align:middle;white-space:nowrap;
                    padding-left:12px;">
                  <div style="display:inline-block;border:1.5px solid #B91C1C;padding:4px 10px;
                       font-family:{_FONT_DISPLAY};font-size:11px;font-weight:600;
                       letter-spacing:3px;text-transform:uppercase;color:#B91C1C;
                       background-color:#F2E8D5;">Dispatch</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td class="mobile-pad" style="padding:20px 24px 8px 24px;">
            <div style="font-family:{_FONT_DISPLAY};font-size:15px;line-height:20px;
                 font-weight:600;letter-spacing:2px;text-transform:uppercase;
                 color:#121212;">{html_module.escape(count_word)}</div>
            <div style="font-family:{_FONT_MONO};font-size:12px;line-height:18px;
                 letter-spacing:1px;color:#6B6358;margin-top:4px;">
              Scanned {html_module.escape(now.strftime('%B %d, %Y at %I:%M %p'))}
            </div>
          </td>
        </tr>

        {shops_html}

        <tr>
          <td class="mobile-pad" style="padding:32px 24px;border-top:1px solid #C9B994;
              text-align:center;">
            <div style="font-family:{_FONT_MONO};font-size:11px;line-height:18px;
                 letter-spacing:3px;text-transform:uppercase;color:#6B6358;">
              Autograph Notifier &middot; Automated Dispatch
            </div>
            <div style="font-family:{_FONT_BODY};font-size:13px;line-height:19px;
                 color:#6B6358;margin-top:10px;font-style:italic;">
              You're receiving this because you asked to be notified about newly signed vinyl &amp; CDs.
            </div>
          </td>
        </tr>

      </table>

    </td>
  </tr>
</table>
</body>
</html>"""


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
    print(f"{'='*60}")
    print(f"  Autograph Notifier — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
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

            print("Scraping shops...\n")
            results = await asyncio.gather(
                scrape_parkave(client),
                scrape_3hive(client, hive_page),
                scrape_sgrecordshop(sg_page),
                scrape_banquet(banquet_page),
                return_exceptions=True,
            )

            await browser.close()

    for r in results:
        if isinstance(r, Exception):
            print(f"  Scraper error: {r}")
        elif isinstance(r, list):
            all_listings.extend(r)

    all_listings = deduplicate_listings(all_listings)
    print(f"\nTotal scraped: {len(all_listings)} listings")

    print("\nComparing with database to detect new listings...")
    new_listings = upsert_listings(conn, all_listings)

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
    print(f"  RESULTS: {len(all_listings)} total, {len(new_listings)} NEW")
    print(f"{'='*60}\n")

    conn.close()
    return new_listings


if __name__ == "__main__":
    asyncio.run(run_scraper())
