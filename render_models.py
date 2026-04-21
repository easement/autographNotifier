from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class SupportsEmailListing(Protocol):
    shop: str
    artist: str
    title: str
    format: str
    signed_by: str
    signature_location: str
    price: str | None
    url: str
    image_url: str | None


@dataclass(frozen=True)
class EmailListingViewModel:
    shop: str
    artist: str
    title: str
    format: str
    signed_by: str
    signature_location: str
    price: str
    url: str
    image_url: str


@dataclass(frozen=True)
class WebListingViewModel:
    hash: str
    shop: str
    artist: str
    title: str
    format: str
    signed_by: str
    signature_location: str
    price: str
    url: str
    image_url: str
    date_added: str


def to_email_listing_view_model(listing: SupportsEmailListing) -> EmailListingViewModel:
    return EmailListingViewModel(
        shop=listing.shop or "",
        artist=listing.artist or "",
        title=listing.title or "",
        format=listing.format or "unknown",
        signed_by=listing.signed_by or "unknown",
        signature_location=listing.signature_location or "unknown",
        price=listing.price or "",
        url=listing.url or "",
        image_url=listing.image_url or "",
    )


def to_web_listing_view_model(raw: Mapping[str, Any]) -> WebListingViewModel:
    return WebListingViewModel(
        hash=str(raw.get("hash", "") or ""),
        shop=str(raw.get("shop", "") or ""),
        artist=str(raw.get("artist", "") or ""),
        title=str(raw.get("title", "") or ""),
        format=str(raw.get("format", "unknown") or "unknown"),
        signed_by=str(raw.get("signed_by", "unknown") or "unknown"),
        signature_location=str(raw.get("signature_location", "unknown") or "unknown"),
        price=str(raw.get("price", "") or ""),
        url=str(raw.get("url", "") or ""),
        image_url=str(raw.get("image_url", "") or ""),
        date_added=str(raw.get("date_added", "") or ""),
    )
