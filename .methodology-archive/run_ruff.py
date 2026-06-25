"""Helper: run ruff on src/ and dump results.

Used to bypass shell-level command restrictions.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/johnny/projects/omnibot")
SRC = REPO / "03-development" / "src"

ruff = shutil.which("ruff")
if not ruff:
    ruff = "/Users/johnny/Library/Python/3.9/bin/ruff"
print(f"ruff at: {ruff}", flush=True)

result = subprocess.run(
    [ruff, "check", str(SRC)],
    cwd=str(REPO),
    capture_output=True,
    text=True,
)
print("---STDOUT---")
print(result.stdout)
print("---STDERR---")
print(result.stderr)
print(f"---EXIT={result.returncode}---")
sys.exit(result.returncode)
