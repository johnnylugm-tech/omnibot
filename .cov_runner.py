"""Coverage runner for FR-22.

Programmatically runs pytest with coverage on test_fr22.py and prints
the term-missing report. Uses sys.executable so the harness venv is picked
up automatically (sys.executable is the venv python when invoked from there).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_FILE = ROOT / "03-development" / "tests" / "test_fr22.py"
SRC_DIR = ROOT / "03-development" / "src"
VENV_PY = ROOT / ".venv" / "bin" / "python3"

# Prefer the venv python (project standard). Fall back to sys.executable.
if VENV_PY.exists():
    python = str(VENV_PY)
else:
    python = sys.executable

cmd = [
    python,
    "-m",
    "pytest",
    str(TEST_FILE),
    f"--cov={SRC_DIR}",
    "--cov-report=term-missing",
    "-q",
]

print("RUN:", " ".join(cmd))
result = subprocess.run(cmd, cwd=str(ROOT))
sys.exit(result.returncode)
