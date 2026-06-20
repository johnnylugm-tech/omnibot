import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
)
sys.stdout.write("=== RUFF OUTPUT ===\n")
sys.stdout.write(result.stdout)
sys.stdout.write(result.stderr)
sys.stdout.write(f"\n=== EXIT CODE: {result.returncode} ===\n")
sys.exit(result.returncode)
