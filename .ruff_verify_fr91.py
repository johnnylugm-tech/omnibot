import subprocess
import sys

result = subprocess.run(
    [".venv/bin/ruff", "check", "03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
sys.stdout.write(result.stdout)
if result.stderr:
    sys.stdout.write("\nSTDERR:\n")
    sys.stdout.write(result.stderr)
sys.stdout.write(f"\nEXIT_CODE: {result.returncode}\n")
sys.exit(result.returncode)
