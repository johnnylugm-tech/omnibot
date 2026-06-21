import subprocess, os, sys
os.chdir("/Users/johnny/projects/omnibot")
r = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "03-development/src/"],
    capture_output=True, text=True,
    timeout=60
)
print(r.stdout)
if r.stderr:
    print(r.stderr, file=sys.stderr)
sys.exit(r.returncode)
