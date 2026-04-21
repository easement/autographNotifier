import unittest

from scraper import Listing, _format_badge_email, _shop_block_html, build_email_html


def make_listing(**overrides):
    defaults = {
        "shop": "Park Ave CDs",
        "artist": "The Artist",
        "title": "Signed Album",
        "format": "LP",
        "signed_by": "band",
        "signature_location": "cover",
        "price": "$29.99",
        "url": "https://example.com/buy",
        "image_url": "https://example.com/image.jpg",
        "description": "A signed release",
    }
    defaults.update(overrides)
    return Listing(**defaults)


class FormatBadgeEmailTests(unittest.TestCase):
    def test_returns_empty_for_unknown_or_blank(self):
        self.assertEqual(_format_badge_email("unknown"), "")
        self.assertEqual(_format_badge_email(""), "")

    def test_uses_cd_blue_and_escapes_label(self):
        badge = _format_badge_email('CD & "Deluxe"')
        self.assertIn("background:#B91C1C", badge)
        self.assertIn("CD &amp; &quot;Deluxe&quot;", badge)

        cd_badge = _format_badge_email("CD")
        self.assertIn("background:#1E3A8A", cd_badge)


class ShopBlockHtmlTests(unittest.TestCase):
    def test_renders_buy_link_meta_and_accessible_image_alt(self):
        listing = make_listing(
            title="Title <One>",
            artist='Artist "One"',
            format="CD",
            signed_by="solo",
            signature_location="insert",
        )
        html = _shop_block_html("Shop <Name>", [listing])

        self.assertIn("Shop &lt;Name&gt;", html)
        self.assertIn('alt="Title &lt;One&gt; by Artist &quot;One&quot;"', html)
        self.assertIn("signed by: solo", html)
        self.assertIn("location: insert", html)
        self.assertIn("v:roundrect", html)
        self.assertIn(">Buy now</a>", html)
        self.assertIn("1 listing", html)

    def test_uses_placeholder_when_image_missing(self):
        listing = make_listing(image_url="", artist="Unknown")
        html = _shop_block_html("No Image Shop", [listing])

        self.assertIn("aria-hidden=\"true\"", html)
        self.assertIn("background:#EADFC7", html)
        self.assertNotIn("<img ", html)


class BuildEmailHtmlTests(unittest.TestCase):
    def test_groups_by_shop_and_renders_preview(self):
        listing_a = make_listing(shop="B Shop", title="First")
        listing_b = make_listing(shop="A Shop", title="Second")
        html = build_email_html([listing_a, listing_b])

        self.assertIn("Dispatches — Autograph Notifier", html)
        self.assertIn("2 new listings", html)
        self.assertIn("across 2 shops", html)
        self.assertLess(html.index("A Shop"), html.index("B Shop"))


if __name__ == "__main__":
    unittest.main()
