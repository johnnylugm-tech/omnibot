#!/usr/bin/env python3
"""Run ruff via the python module API to capture violations."""
import sys
from pathlib import Path

# Add ruff's location to path
ruff_bin = Path("/Users/johnny/Library/Python/3.9/bin/ruff")
sys.path.insert(0, str(ruff_bin.parent.parent / "lib/python3.9/site-packages"))

try:
    from ruff import __main__ as ruff_main
    sys.argv = ["ruff", "check", "03-development/src/"]
    ruff_main.main()
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(2)