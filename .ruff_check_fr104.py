"""Run ruff check and capture output."""
import subprocess, os
os.chdir("/Users/johnny/projects/omnibot")
r = subprocess.run(["ruff", "check", "03-development/src/"], capture_output=True, text=True)
print("STDOUT:"); print(r.stdout or "(empty)")
print("STDERR:"); print(r.stderr or "(empty)")
print("EXIT:", r.returncode)
