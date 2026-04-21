import unittest

from render_models import to_email_listing_view_model, to_web_listing_view_model
from scraper import Listing


class RenderModelConversionTests(unittest.TestCase):
    def test_email_view_model_defaults_optional_fields(self):
        listing = Listing(
            shop="Shop",
            artist="Artist",
            title="Title",
            format="LP",
            signed_by="unknown",
            signature_location="unknown",
            price=None,
            url="https://example.com",
            image_url=None,
            description=None,
        )

        vm = to_email_listing_view_model(listing)

        self.assertEqual(vm.price, "")
        self.assertEqual(vm.image_url, "")
        self.assertEqual(vm.shop, "Shop")

    def test_web_view_model_defaults_missing_values(self):
        vm = to_web_listing_view_model({"title": "Only Title"})

        self.assertEqual(vm.title, "Only Title")
        self.assertEqual(vm.hash, "")
        self.assertEqual(vm.format, "unknown")
        self.assertEqual(vm.date_added, "")


if __name__ == "__main__":
    unittest.main()
