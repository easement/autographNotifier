import unittest
from datetime import date

from generate_html import _format_date_label, generate_html


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


if __name__ == "__main__":
    unittest.main()
