import subprocess
import sys

result = subprocess.run(
    [".venv/bin/ruff", "check", "03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
