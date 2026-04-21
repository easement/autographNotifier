"""Tests for the 13 new record store scrapers."""
import unittest
from unittest.mock import AsyncMock, patch

from scraper import (
    Listing,
    scrape_assai,
    scrape_cleorecs,
    scrape_darksiderecords,
    scrape_fingerprints,
    scrape_looneytunes,
    scrape_musicrecordshop,
    scrape_nailcityrecord,
    scrape_plaidroomrecords,
    scrape_rarelimiteds,
    scrape_rarevinyl,
    scrape_roughtrade,
    scrape_seasick,
    scrape_ziarecords,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _product_page(
    title="Test LP - Signed",
    artist="Test Artist",
    price="$29.99",
    url="https://example.com/products/test",
    image_url="https://example.com/image.jpg",
) -> str:
    return f"""<html><body>
    <div class="product-item">
        <a href="{url}">
            <img src="{image_url}">
            <h3>{title}</h3>
            <span class="artist">{artist}</span>
            <span class="price">{price}</span>
        </a>
    </div>
    </body></html>"""


EMPTY_PAGE = "<html><body></body></html>"


def _paginated_page_mock(first_html: str, second_html: str = EMPTY_PAGE) -> AsyncMock:
    """Page mock for scrapers that paginate: returns first_html then second_html."""
    page = AsyncMock()
    page.content.side_effect = [first_html, second_html]
    return page


def _scroll_page_mock(html: str) -> AsyncMock:
    """Page mock for infinite-scroll scrapers: returns height 0 to break the loop."""
    page = AsyncMock()
    page.content.return_value = html
    page.evaluate.side_effect = lambda expr: None if "scrollTo" in expr else 0
    return page


# ─── Shopify JSON Wrappers ────────────────────────────────────────────────────

class TestShopifyWrappers(unittest.IsolatedAsyncioTestCase):
    """Each scraper is a thin wrapper around scrape_shopify(); verify the URL contract."""

    async def _assert_shopify_args(self, fn, expected_url, expected_shop, expected_base):
        client = AsyncMock()
        with patch("scraper.scrape_shopify", new=AsyncMock(return_value=[])) as mock:
            await fn(client)
        mock.assert_called_once_with(client, expected_url, expected_shop, expected_base)

    async def test_nailcityrecord(self):
        await self._assert_shopify_args(
            scrape_nailcityrecord,
            "https://nailcityrecord.com/collections/autographed-signed-editions/products.json",
            "Nail City Record",
            "https://nailcityrecord.com",
        )

    async def test_darksiderecords(self):
        await self._assert_shopify_args(
            scrape_darksiderecords,
            "https://shop.darksiderecords.com/collections/autographed-items/products.json",
            "Darkside Records",
            "https://shop.darksiderecords.com",
        )

    async def test_assai(self):
        await self._assert_shopify_args(
            scrape_assai,
            "https://assai.co.uk/collections/signed-vinyl/products.json",
            "Assai Records",
            "https://assai.co.uk",
        )

    async def test_musicrecordshop(self):
        await self._assert_shopify_args(
            scrape_musicrecordshop,
            "https://musicrecordshop.com/collections/signed-vinyl/products.json",
            "Music Record Shop",
            "https://musicrecordshop.com",
        )

    async def test_rarelimiteds(self):
        await self._assert_shopify_args(
            scrape_rarelimiteds,
            "https://rarelimiteds.com/collections/autographed/products.json",
            "Rare Limiteds",
            "https://rarelimiteds.com",
        )

    async def test_cleorecs(self):
        await self._assert_shopify_args(
            scrape_cleorecs,
            "https://cleorecs.com/collections/signed-items/products.json",
            "Cleo Recs",
            "https://cleorecs.com",
        )


# ─── Zia Records ──────────────────────────────────────────────────────────────

class TestZiaRecords(unittest.IsolatedAsyncioTestCase):
    async def test_parses_listing_fields(self):
        html = _product_page(
            title="Artist - Signed Album LP",
            artist="Artist",
            price="$35.00",
            url="https://www.ziarecords.com/p/1234/test",
        )
        listings = await scrape_ziarecords(_paginated_page_mock(html))
        self.assertEqual(len(listings), 1)
        lst = listings[0]
        self.assertEqual(lst.shop, "Zia Records")
        self.assertEqual(lst.title, "Artist - Signed Album LP")
        self.assertEqual(lst.artist, "Artist")
        self.assertEqual(lst.price, "$35.00")
        self.assertEqual(lst.url, "https://www.ziarecords.com/p/1234/test")
        self.assertEqual(lst.format, "LP")

    async def test_stops_on_empty_page(self):
        listings = await scrape_ziarecords(_paginated_page_mock(_product_page()))
        self.assertEqual(len(listings), 1)

    async def test_normalizes_protocol_relative_image(self):
        html = _product_page(image_url="//www.ziarecords.com/img/cover.jpg")
        listings = await scrape_ziarecords(_paginated_page_mock(html))
        self.assertEqual(listings[0].image_url, "https://www.ziarecords.com/img/cover.jpg")

    async def test_resolves_relative_product_url(self):
        html = _product_page(url="/p/1234/test-album")
        listings = await scrape_ziarecords(_paginated_page_mock(html))
        self.assertEqual(listings[0].url, "https://www.ziarecords.com/p/1234/test-album")

    async def test_returns_empty_when_no_products(self):
        listings = await scrape_ziarecords(_paginated_page_mock(EMPTY_PAGE, EMPTY_PAGE))
        self.assertEqual(listings, [])


# ─── Rare Vinyl ───────────────────────────────────────────────────────────────

class TestRareVinyl(unittest.IsolatedAsyncioTestCase):
    async def test_parses_listing_fields(self):
        html = _product_page(
            title="Autographed Album",
            artist="Some Artist",
            url="https://us.rarevinyl.com/collections/autographs/products/test",
        )
        listings = await scrape_rarevinyl(_paginated_page_mock(html))
        self.assertEqual(len(listings), 1)
        lst = listings[0]
        self.assertEqual(lst.shop, "Rare Vinyl")
        self.assertEqual(lst.title, "Autographed Album")
        self.assertEqual(lst.artist, "Some Artist")

    async def test_stops_on_empty_page(self):
        listings = await scrape_rarevinyl(_paginated_page_mock(_product_page()))
        self.assertEqual(len(listings), 1)

    async def test_deduplicates_same_url(self):
        html = """<html><body>
        <div class="product-item">
            <a href="https://us.rarevinyl.com/products/dup"><h3>Album</h3></a>
        </div>
        <div class="product-item">
            <a href="https://us.rarevinyl.com/products/dup"><h3>Album</h3></a>
        </div>
        </body></html>"""
        listings = await scrape_rarevinyl(_paginated_page_mock(html))
        self.assertEqual(len(listings), 1)


# ─── Rough Trade ──────────────────────────────────────────────────────────────

class TestRoughTrade(unittest.IsolatedAsyncioTestCase):
    async def test_parses_listing_fields(self):
        html = _product_page(
            title="Signed Deluxe Edition LP",
            url="https://www.roughtrade.com/en-us/product/test",
        )
        listings = await scrape_roughtrade(_scroll_page_mock(html))
        self.assertEqual(len(listings), 1)
        lst = listings[0]
        self.assertEqual(lst.shop, "Rough Trade")
        self.assertEqual(lst.title, "Signed Deluxe Edition LP")

    async def test_returns_empty_when_no_products(self):
        listings = await scrape_roughtrade(_scroll_page_mock(EMPTY_PAGE))
        self.assertEqual(listings, [])

    async def test_deduplicates_same_url(self):
        html = """<html><body>
        <div class="product-item">
            <a href="https://www.roughtrade.com/en-us/product/dup"><h3>Album</h3></a>
        </div>
        <div class="product-item">
            <a href="https://www.roughtrade.com/en-us/product/dup"><h3>Album</h3></a>
        </div>
        </body></html>"""
        listings = await scrape_roughtrade(_scroll_page_mock(html))
        self.assertEqual(len(listings), 1)


# ─── Looney Tunes Long Island ─────────────────────────────────────────────────

class TestLooneyTunes(unittest.IsolatedAsyncioTestCase):
    async def test_parses_listing_fields(self):
        html = _product_page(
            title="Signed Beatles LP",
            artist="The Beatles",
            price="$199.99",
            url="https://www.looneytuneslongisland.com/item/123",
        )
        listings = await scrape_looneytunes(_paginated_page_mock(html))
        self.assertEqual(len(listings), 1)
        lst = listings[0]
        self.assertEqual(lst.shop, "Looney Tunes Long Island")
        self.assertEqual(lst.title, "Signed Beatles LP")
        self.assertEqual(lst.price, "$199.99")

    async def test_stops_on_empty_page(self):
        listings = await scrape_looneytunes(_paginated_page_mock(_product_page()))
        self.assertEqual(len(listings), 1)

    async def test_normalizes_protocol_relative_image(self):
        html = _product_page(image_url="//www.looneytuneslongisland.com/img/item.jpg")
        listings = await scrape_looneytunes(_paginated_page_mock(html))
        self.assertEqual(listings[0].image_url, "https://www.looneytuneslongisland.com/img/item.jpg")


# ─── Fingerprints Music ───────────────────────────────────────────────────────

class TestFingerprints(unittest.IsolatedAsyncioTestCase):
    async def test_parses_listing_fields(self):
        html = _product_page(
            title="Autographed CD",
            url="https://shop.fingerprintsmusic.com/Product/Detail/test",
        )
        listings = await scrape_fingerprints(_paginated_page_mock(html))
        self.assertEqual(len(listings), 1)
        lst = listings[0]
        self.assertEqual(lst.shop, "Fingerprints Music")
        self.assertEqual(lst.title, "Autographed CD")
        self.assertEqual(lst.format, "CD")

    async def test_stops_on_empty_page(self):
        listings = await scrape_fingerprints(_paginated_page_mock(_product_page()))
        self.assertEqual(len(listings), 1)

    async def test_resolves_relative_product_url(self):
        html = _product_page(url="/Product/Detail/test")
        listings = await scrape_fingerprints(_paginated_page_mock(html))
        self.assertEqual(listings[0].url, "https://shop.fingerprintsmusic.com/Product/Detail/test")


# ─── Plaid Room Records ───────────────────────────────────────────────────────

class TestPlaidRoomRecords(unittest.IsolatedAsyncioTestCase):
    async def test_parses_listing_fields(self):
        html = _product_page(
            title="Signed Exclusive LP",
            url="https://www.plaidroomrecords.com/products/test",
        )
        listings = await scrape_plaidroomrecords(_scroll_page_mock(html))
        self.assertEqual(len(listings), 1)
        lst = listings[0]
        self.assertEqual(lst.shop, "Plaid Room Records")
        self.assertEqual(lst.title, "Signed Exclusive LP")

    async def test_returns_empty_when_no_products(self):
        listings = await scrape_plaidroomrecords(_scroll_page_mock(EMPTY_PAGE))
        self.assertEqual(listings, [])

    async def test_resolves_relative_product_url(self):
        html = _product_page(url="/products/signed-lp")
        listings = await scrape_plaidroomrecords(_scroll_page_mock(html))
        self.assertEqual(listings[0].url, "https://www.plaidroomrecords.com/products/signed-lp")


# ─── Seasick Birmingham ───────────────────────────────────────────────────────

class TestSeasick(unittest.IsolatedAsyncioTestCase):
    async def test_includes_autographed_items(self):
        html = _product_page(title="Autographed LP by Band")
        listings = await scrape_seasick(_scroll_page_mock(html))
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].shop, "Seasick Birmingham")

    async def test_includes_signed_items(self):
        html = _product_page(title="Signed Exclusive Album")
        listings = await scrape_seasick(_scroll_page_mock(html))
        self.assertEqual(len(listings), 1)

    async def test_excludes_items_without_signed_or_autograph(self):
        html = _product_page(title="Regular Album No Signature")
        listings = await scrape_seasick(_scroll_page_mock(html))
        self.assertEqual(len(listings), 0)

    async def test_deduplicates_same_url(self):
        html = """<html><body>
        <div class="product-item">
            <a href="https://seasickbham.com/products/dup"><h3>Signed Album</h3></a>
        </div>
        <div class="product-item">
            <a href="https://seasickbham.com/products/dup"><h3>Signed Album</h3></a>
        </div>
        </body></html>"""
        listings = await scrape_seasick(_scroll_page_mock(html))
        self.assertEqual(len(listings), 1)


if __name__ == "__main__":
    unittest.main()
