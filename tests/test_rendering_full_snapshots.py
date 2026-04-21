import hashlib
import unittest

from tests.render_snapshot_data import normalize_email_html, sample_email_html, sample_web_html
from tests.snapshot_utils import assert_snapshot


class RenderingFullSnapshotTests(unittest.TestCase):
    def test_email_full_snapshot_hash(self):
        html = normalize_email_html(sample_email_html())
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        assert_snapshot("email_full.sha256", digest)

    def test_web_full_snapshot_hash(self):
        html = sample_web_html()
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        assert_snapshot("web_full.sha256", digest)


if __name__ == "__main__":
    unittest.main()
