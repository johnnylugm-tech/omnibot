"""Run ruff check on 03-development/src/ and print the result."""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-c", "from ruff.__main__ import main; main()", "check", "03-development/src/"],
    capture_output=True,
    text=True,
)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("EXIT:", result.returncode)
sys.exit(result.returncode)
