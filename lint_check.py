"""Run ruff check and print results."""
import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check",
     "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot"
)
print(result.stdout)
print(result.stderr)
print("EXIT:", result.returncode)
sys.exit(result.returncode)
