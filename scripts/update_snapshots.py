from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from render_snapshot_data import (
    email_head_fragment,
    normalize_email_html,
    normalize_web_html,
    sample_email_html,
    sample_web_html,
    web_header_fragment,
)


def write_snapshot(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def main() -> None:
    snapshot_dir = Path("tests/snapshots")

    email_html = normalize_email_html(sample_email_html())
    web_html = normalize_web_html(sample_web_html())

    write_snapshot(snapshot_dir / "email_head_fragment.snap", email_head_fragment(email_html))
    write_snapshot(snapshot_dir / "web_header_fragment.snap", web_header_fragment(web_html))

    email_hash = hashlib.sha256(email_html.encode("utf-8")).hexdigest()
    web_hash = hashlib.sha256(web_html.encode("utf-8")).hexdigest()
    write_snapshot(snapshot_dir / "email_full.sha256.snap", email_hash)
    write_snapshot(snapshot_dir / "web_full.sha256.snap", web_hash)


if __name__ == "__main__":
    main()
