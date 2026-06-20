"""Run ruff check and write results to a local file."""
import subprocess
import sys

result = subprocess.run(
    ["ruff", "check", "03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
with open("/Users/johnny/projects/omnibot/.ruff_check_result.txt", "w") as f:
    f.write(f"EXIT: {result.returncode}\n")
    f.write("STDOUT:\n")
    f.write(result.stdout)
    f.write("\nSTDERR:\n")
    f.write(result.stderr)
sys.exit(result.returncode)