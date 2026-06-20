import subprocess, sys
r = subprocess.run(["/Users/johnny/Library/Python/3.9/bin/ruff","check","03-development/src/"], capture_output=True, text=True)
print("EXIT", r.returncode)
print("STDOUT", r.stdout)
print("STDERR", r.stderr)
sys.exit(r.returncode)
