"""Run ruff check and print the results."""
import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check",
     "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("EXIT:", result.returncode)
sys.exit(result.returncode)
