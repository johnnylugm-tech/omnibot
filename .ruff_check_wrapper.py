"""Wrapper to run ruff check via subprocess."""
import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
sys.stdout.write("STDOUT:" + result.stdout + "\n")
sys.stdout.write("STDERR:" + result.stderr + "\n")
sys.stdout.write("EXIT:" + str(result.returncode) + "\n")
sys.stdout.flush()
sys.exit(result.returncode)