"""Invokes lint tool via its Python API."""
import sys


def _find_lib():
    candidates = [
        "/Users/johnny/Library/Python/3.9/lib/python/site-packages",
        "/Users/johnny/Library/Python/3.9/lib/python3.9/site-packages",
    ]
    for c in candidates:
        if c not in sys.path:
            sys.path.insert(0, c)


_find_lib()

try:
    from ruff.__main__ import main as entrypoint
except Exception as exc:  # noqa: BLE001
    print(f"tool import failed: {exc!r}", file=sys.stderr)
    sys.exit(2)

sys.argv = ["ruff", "check", "03-development/src/"]
entrypoint()
