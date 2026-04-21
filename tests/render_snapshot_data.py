import re

from generate_html import generate_html
from scraper import Listing, build_email_html


def sample_email_html() -> str:
    listing = Listing(
        shop="Snapshot Shop",
        artist="Snapshot Artist",
        title="Snapshot Title",
        format="LP",
        signed_by="band",
        signature_location="cover",
        price="$33",
        url="https://example.com/item",
        image_url="https://example.com/item.jpg",
        description="signed release",
    )
    return build_email_html([listing])


def sample_web_html() -> str:
    listings = [
        {
            "hash": "snap1",
            "shop": "Snapshot Shop",
            "artist": "Snapshot Artist",
            "title": "Snapshot Title",
            "format": "CD",
            "signed_by": "solo",
            "signature_location": "insert",
            "price": "$22",
            "url": "https://example.com/item",
            "image_url": "https://example.com/item.jpg",
            "date_added": "2026-01-02",
        }
    ]
    return generate_html(listings)


def normalize_email_html(html: str) -> str:
    normalized = re.sub(r"Scanned [^<]+", "Scanned <TIMESTAMP>", html)
    normalized = re.sub(r"scanned [^.]+\.", "scanned <PREVIEW_TIMESTAMP>.", normalized)
    return normalized


def email_head_fragment(html: str) -> str:
    start = html.index("<meta http-equiv=\"X-UA-Compatible\"")
    end = html.index("</title>") + len("</title>")
    return html[start:end]


def web_header_fragment(html: str) -> str:
    start = html.index("<header class=\"site-header\">")
    end = html.index("</header>") + len("</header>")
    return html[start:end]
