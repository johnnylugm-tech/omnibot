"""Lint check using ruff's python module API."""
import sys
from pathlib import Path

# Add venv site-packages to path
venv_site = Path("/Users/johnny/projects/omnibot/.venv/lib/python3.11/site-packages")
sys.path.insert(0, str(venv_site))

# Patch ruff to use the actual binary
import ruff.__main__ as ruff_main
ruff_main.find_ruff = lambda: "/Users/johnny/projects/omnibot/.venv/bin/ruff"

sys.argv = ["ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"]
try:
    ruff_main.main()
except SystemExit as e:
    print(f"\n=== LINT EXIT: {e.code} ===")
    raise
