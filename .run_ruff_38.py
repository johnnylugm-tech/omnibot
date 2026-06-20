import subprocess
import sys

result = subprocess.run(
    ["/Users/johnny/Library/Python/3.9/bin/ruff", "check", "03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("EXIT:", result.returncode)
sys.exit(0)
