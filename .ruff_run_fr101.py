"""Run ruff check on src directory for FR-101 lint fix."""
import shutil
import subprocess
import sys

ruff = shutil.which("ruff") or "/Users/johnny/Library/Python/3.9/bin/ruff"
result = subprocess.run(
    [ruff, "check", "03-development/src/"],
    capture_output=True,
    text=True,
)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("EXIT:", result.returncode)
sys.exit(result.returncode)
