"""Capture ruff output to file for FR-96 lint fix."""
import subprocess
from pathlib import Path

OUT = Path("/Users/johnny/projects/omnibot/.ruff_out_fr96.txt")
RUFF = Path("/Users/johnny/projects/omnibot/.venv/bin/ruff")
TARGET = Path("/Users/johnny/projects/omnibot/03-development/src/")

r = subprocess.run(
    [str(RUFF), "check", str(TARGET)],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
OUT.write_text(
    f"STDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}\nEXIT: {r.returncode}\n"
)
print(f"EXIT={r.returncode}; lines={len(r.stdout.splitlines())}")