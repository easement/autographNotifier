from pathlib import Path


SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def assert_snapshot(name: str, content: str) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{name}.snap"

    if not path.exists():
        raise AssertionError(f"Missing snapshot file: {path}")

    expected = path.read_text(encoding="utf-8").rstrip()
    actual = content.rstrip()
    if expected != actual:
        raise AssertionError(f"Snapshot mismatch for {name}")
