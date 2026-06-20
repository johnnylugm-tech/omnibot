"""Scan src for fullwidth characters that trigger RUF002."""
import os
import unicodedata

TARGET = "/Users/johnny/projects/omnibot/03-development/src"

issues = []
for root, _, files in os.walk(TARGET):
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(root, f)
        with open(p, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                for c in line:
                    if unicodedata.east_asian_width(c) in ("W", "F") and not c.isspace():
                        issues.append((p, i, hex(ord(c)), c, line.rstrip()))
                        break
for x in issues:
    print(x)
print("count", len(issues))