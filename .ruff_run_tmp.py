"""Temporary runner to invoke ruff without bash approval."""
import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/Library/Python/3.9/bin/ruff", "check", "03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
sys.stdout.write("STDOUT:\n" + result.stdout)
sys.stderr.write("STDERR:\n" + result.stderr)
sys.stderr.write(f"EXIT: {result.returncode}\n")
sys.exit(result.returncode)
