import unittest

from tests.render_snapshot_data import (
    email_head_fragment,
    normalize_email_html,
    sample_email_html,
    sample_web_html,
    web_header_fragment,
)
from tests.snapshot_utils import assert_snapshot


class RenderingSnapshotTests(unittest.TestCase):
    def test_email_header_snapshot(self):
        html = sample_email_html()
        normalized = normalize_email_html(html)
        fragment = email_head_fragment(normalized)
        assert_snapshot("email_head_fragment", fragment)

    def test_web_header_snapshot(self):
        html = sample_web_html()
        fragment = web_header_fragment(html)
        assert_snapshot("web_header_fragment", fragment)


if __name__ == "__main__":
    unittest.main()
