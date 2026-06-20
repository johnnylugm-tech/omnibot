"""Verify ruff check on 03-development/src/."""
import subprocess
import sys

r = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check",
     "/Users/johnny/projects/omnibot/03-development/src/",
     "--output-format=concise"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
sys.stdout.write("STDOUT:\n")
sys.stdout.write(r.stdout)
sys.stdout.write("\nSTDERR:\n")
sys.stdout.write(r.stderr)
sys.stdout.write(f"\nEXIT_CODE: {r.returncode}\n")
sys.exit(r.returncode)
