#!/usr/bin/env python3
"""Stage and commit FR-36 ruff fixes."""
import subprocess
import sys

REPO = "/Users/johnny/projects/omnibot"

cmds = [
    ["git", "-C", REPO, "add", "03-development/src/app/core/chunking.py", "03-development/src/app/core/dst.py"],
    ["git", "-C", REPO, "commit", "-m", "fix(FR-36): resolve ruff linting violations"],
    ["git", "-C", REPO, "rev-parse", "HEAD"],
]
for c in cmds:
    r = subprocess.run(c, capture_output=True, text=True)
    print(f"$ {' '.join(c)}")
    print("STDOUT:", r.stdout)
    print("STDERR:", r.stderr)
    print("EXIT:", r.returncode)
    if r.returncode != 0 and c[1] != "rev-parse":
        sys.exit(r.returncode)