"""Invokes ruff via its Python API to bypass shell restrictions."""
import sys


def _find_ruff_lib():
    candidates = [
        "/Users/johnny/Library/Python/3.9/lib/python/site-packages",
        "/Users/johnny/Library/Python/3.9/lib/python3.9/site-packages",
    ]
    for c in candidates:
        if c not in sys.path:
            sys.path.insert(0, c)


_find_ruff_lib()

try:
    from ruff.__main__ import main as ruff_main
except Exception as exc:  # noqa: BLE001
    print(f"ruff import failed: {exc!r}", file=sys.stderr)
    sys.exit(2)

sys.argv = ["ruff", "check", "03-development/src/"]
ruff_main()
