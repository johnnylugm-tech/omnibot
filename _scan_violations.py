"""Run ruff and print all violations."""
import subprocess
import sys

r = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check",
     "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True, text=True,
)
print("STDOUT:")
print(r.stdout)
print("STDERR:")
print(r.stderr)
print(f"EXIT: {r.returncode}")