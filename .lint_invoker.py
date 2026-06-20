"""Wrapper to run linter."""
import subprocess
import sys

result = subprocess.run(
    ['/Users/johnny/projects/omnibot/.venv/bin/ruff', 'check', '/Users/johnny/projects/omnibot/03-development/src/'],
    capture_output=True,
    text=True,
    cwd='/Users/johnny/projects/omnibot',
)
sys.stdout.write("STDOUT:\n")
sys.stdout.write(result.stdout)
sys.stdout.write("\nSTDERR:\n")
sys.stdout.write(result.stderr)
sys.stdout.write(f"\nEXIT_CODE: {result.returncode}\n")
sys.exit(result.returncode)