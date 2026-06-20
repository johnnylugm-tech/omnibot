import subprocess
result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
)
import sys
sys.stdout.write(result.stdout)
sys.stdout.write(result.stderr)
sys.stdout.write("RC: " + str(result.returncode) + "\n")
sys.stdout.flush()
