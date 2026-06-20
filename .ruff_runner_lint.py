#!/usr/bin/env python3
"""Run ruff check on the src directory."""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "03-development/src/"],
    capture_output=True,
    text=True,
)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print(f"EXIT: {result.returncode}")
sys.exit(result.returncode)