"""Verify ruff exits 0 on 03-development/src/."""
import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check",
     "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
