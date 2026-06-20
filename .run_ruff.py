import os
import sys
os.execve(
    "/Users/johnny/Library/Python/3.9/bin/ruff",
    ["ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    os.environ.copy(),
)