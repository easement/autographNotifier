import unittest
from datetime import date

from generate_html import _format_date_label, filter_listings_from_past_days, generate_html


class GenerateHtmlRenderingTests(unittest.TestCase):
    def test_format_date_label_handles_invalid_and_valid_values(self):
        self.assertEqual(_format_date_label(""), "Unknown Date")
        self.assertEqual(_format_date_label("bad-value"), "bad-value")
        self.assertIn("January 2", _format_date_label("2026-01-02"))

    def test_generate_html_renders_new_theme_content_and_badges(self):
        today = date.today().isoformat()
        listings = [
            {
                "hash": "abc123",
                "shop": "Shop One",
                "artist": "Artist One",
                "title": "Great <Album>",
                "format": "CD",
                "signed_by": "solo",
                "signature_location": "insert",
                "price": "$30",
                "url": "https://example.com/1",
                "image_url": "https://example.com/1.jpg",
                "date_added": today,
            },
            {
                "hash": "def456",
                "shop": "Shop Two",
                "artist": "Artist Two",
                "title": "No Image Album",
                "format": "unknown",
                "signed_by": "unknown",
                "signature_location": "unknown",
                "price": "",
                "url": "",
                "image_url": "",
                "date_added": today,
            },
        ]

        html = generate_html(listings)

        self.assertIn("<title>Dispatches — Autograph Notifier</title>", html)
        self.assertIn("Autograph<span>&nbsp;Notifier</span>", html)
        self.assertIn("Signed · Sealed · Delivered", html)
        self.assertIn("class=\"today-badge\">Today</span>", html)
        self.assertIn("format-badge", html)
        self.assertIn("background:#2e8b57", html)
        self.assertIn("Great &lt;Album&gt;", html)
        self.assertIn("thumb-placeholder", html)
        self.assertIn("Search titles, artists…", html)

    def test_filter_listings_from_past_days_includes_only_recent_window(self):
        listings = [
            {"hash": "today", "date_added": "2026-04-22"},
            {"hash": "boundary", "date_added": "2026-04-16"},
            {"hash": "too_old", "date_added": "2026-04-15"},
            {"hash": "future", "date_added": "2026-04-23"},
            {"hash": "invalid", "date_added": "not-a-date"},
            {"hash": "missing", "date_added": ""},
        ]
        filtered = filter_listings_from_past_days(
            listings=listings,
            days=7,
            today=date(2026, 4, 22),
        )
        self.assertEqual([item["hash"] for item in filtered], ["today", "boundary"])


if __name__ == "__main__":
    unittest.main()
