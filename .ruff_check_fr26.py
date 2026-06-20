import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/Library/Python/3.9/bin/ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
)
sys.stdout.write("STDOUT:\n")
sys.stdout.write(result.stdout)
sys.stdout.write("\nSTDERR:\n")
sys.stdout.write(result.stderr)
sys.stdout.write(f"\nRC: {result.returncode}\n")
sys.stdout.flush()
sys.exit(result.returncode)