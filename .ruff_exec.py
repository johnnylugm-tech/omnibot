"""Execute ruff check programmatically."""
import sys
import subprocess

ruff_bin = "/Users/johnny/Library/Python/3.9/bin/ruff"
result = subprocess.run(
    [ruff_bin, "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
sys.stdout.write("STDOUT:\n")
sys.stdout.write(result.stdout)
sys.stdout.write("STDERR:\n")
sys.stdout.write(result.stderr)
sys.stdout.write(f"\nEXIT_CODE: {result.returncode}\n")
sys.exit(result.returncode)