"""Check 03-development/src via ruff python API."""
import os
import sys

# Add the venv site-packages
sys.path.insert(0, "/Users/johnny/projects/omnibot/.venv/lib/python3.11/site-packages")

# Use the ruff python API directly
try:
    from ruff import __main__ as ruff_main
    # Patch the find_ruff to return the venv binary
    ruff_main.find_ruff = lambda: "/Users/johnny/projects/omnibot/.venv/bin/ruff"
    sys.argv = ["ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"]
    ruff_main.main()
except SystemExit as e:
    print(f"\nEXIT={e.code}", file=sys.stderr)
    sys.exit(e.code if e.code is not None else 0)
except Exception as e:
    print(f"ERROR: {e!r}", file=sys.stderr)
    sys.exit(2)
