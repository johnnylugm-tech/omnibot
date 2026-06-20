"""Run ruff check on 03-development/src/."""
import subprocess
import sys

r = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check",
     "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
sys.stdout.write(r.stdout)
sys.stdout.write(r.stderr)
sys.stdout.write(f"\nEXIT: {r.returncode}\n")
sys.exit(r.returncode)
