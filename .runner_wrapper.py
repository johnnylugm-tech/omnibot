import os
import subprocess
import sys

os.chdir("/Users/johnny/projects/omnibot")

print("=== LINT RUNNER ===")
r1 = subprocess.run(
    [".venv/bin/python3", ".lint_runner.py"],
    capture_output=True,
    text=True,
)
sys.stdout.write("STDOUT:\n")
sys.stdout.write(r1.stdout)
sys.stdout.write("STDERR:\n")
sys.stdout.write(r1.stderr)
sys.stdout.write(f"EXIT_CODE: {r1.returncode}\n")
sys.stdout.write("=== END LINT ===\n\n")

print("=== PYTEST RUNNER ===")
r2 = subprocess.run(
    [".venv/bin/python3", "-m", "pytest", "tests/test_fr21.py", "-q"],
    capture_output=True,
    text=True,
)
sys.stdout.write("STDOUT:\n")
sys.stdout.write(r2.stdout)
sys.stdout.write("STDERR:\n")
sys.stdout.write(r2.stderr)
sys.stdout.write(f"EXIT_CODE: {r2.returncode}\n")
sys.stdout.write("=== END PYTEST ===\n")