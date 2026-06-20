import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("RC:", result.returncode)
sys.exit(result.returncode)
