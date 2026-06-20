"""Run ruff and dump violations to stdout. Used by LINT-FIX step."""
import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check",
     "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
)
sys.stdout.write("STDOUT:\n" + result.stdout + "\n")
sys.stdout.write("STDERR:\n" + result.stderr + "\n")
sys.stdout.write(f"RC: {result.returncode}\n")
sys.stdout.flush()
