"""Run ruff check and print results."""
import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/Library/Python/3.9/bin/ruff", "check", "03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
print(f"EXIT: {result.returncode}")
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
sys.exit(result.returncode)
