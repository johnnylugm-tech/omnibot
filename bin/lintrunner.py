import subprocess
import sys

binary = "/Users/johnny/projects/omnibot/.venv/bin/ruff"
result = subprocess.run(
    [binary, "check", "/Users/johnny/projects/omnibot/03-development/src/",
     "--extend-ignore", "RUF001,RUF002,RUF003"],
    capture_output=True, text=True
)
sys.stdout.write(result.stdout)
sys.stdout.write("\n---STDERR---\n")
sys.stdout.write(result.stderr)
sys.stdout.write(f"\n---EXIT: {result.returncode}---\n")
sys.exit(result.returncode)