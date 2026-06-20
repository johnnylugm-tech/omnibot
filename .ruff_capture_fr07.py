"""Capture ruff check output to a file for FR-07 lint fix."""
import subprocess
from pathlib import Path

ROOT = Path("/Users/johnny/projects/omnibot")
RUFF = ROOT / ".venv/bin/ruff"

result = subprocess.run(
    [str(RUFF), "check", str(ROOT / "03-development/src/")],
    capture_output=True,
    text=True,
    cwd=str(ROOT),
)
out = (
    f"EXIT: {result.returncode}\n"
    f"--- STDOUT ---\n{result.stdout}\n"
    f"--- STDERR ---\n{result.stderr}\n"
)
(ROOT / ".ruff_fr07_out.txt").write_text(out)
print(out)