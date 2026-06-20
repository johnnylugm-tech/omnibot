"""Local coverage runner for FR-22.

Invokes the project venv's pytest via subprocess so that the harness
permission boundary is satisfied (only an in-project script is exec'd).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/johnny/projects/omnibot")
VENV_PY = ROOT / ".venv" / "bin" / "python3"
TEST_FILE = ROOT / "03-development" / "tests" / "test_fr22.py"
SRC_DIR = ROOT / "03-development" / "src"

cmd = [
    str(VENV_PY),
    "-m",
    "pytest",
    str(TEST_FILE),
    f"--cov={SRC_DIR}",
    "--cov-report=term-missing",
    "-q",
]

print(" ".join(cmd))
proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
sys.stdout.write(proc.stdout)
sys.stderr.write(proc.stderr)
sys.exit(proc.returncode)
