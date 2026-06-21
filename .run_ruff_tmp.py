import subprocess, sys
result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check", "03-development/src/"],
    cwd="/Users/johnny/projects/omnibot",
    capture_output=True,
    text=True,
)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
