"""Run ruff check on src directory for FR-69 lint fix."""
import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/Library/Python/3.9/bin/ruff", "check", "03-development/src/"],
    capture_output=True,
    text=True,
)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("EXIT:", result.returncode)
sys.exit(result.returncode)
