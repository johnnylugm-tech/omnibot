"""Run lint check using ruff's library API directly."""
import sys
from pathlib import Path

# Add venv site-packages to path
venv_site = Path("/Users/johnny/projects/omnibot/.venv/lib/python3.11/site-packages")
sys.path.insert(0, str(venv_site))

from ruff.api import lint

results = lint(
    "/Users/johnny/projects/omnibot/03-development/src/",
    select=["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "RUF"],
    ignore=["E501", "B008", "B904"],
    line_length=100,
    target_version="py311",
    extend_exclude=["harness", ".sessi-work", ".ruff_cache", "__pycache__"],
)

print("=== LINT RESULTS ===")
print(f"Violations: {len(results[1])}")
for v in results[1]:
    print(f"  {v}")
print(f"=== EXIT: {results[0]} ===")
sys.exit(results[0])
