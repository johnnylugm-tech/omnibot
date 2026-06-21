import re
from collections import defaultdict

with open("03-development/.audit/bug-report-2026-06-21.md", "r") as f:
    lines = f.readlines()

bugs = []
current_bug = None

for line in lines:
    m1 = re.match(r'#### ([CH]-\d+) · `(.*?)` — (.*)', line)
    if m1:
        if current_bug:
            bugs.append(current_bug)
        files = [f.strip() for f in m1.group(2).split('+')]
        # Extract base file names if line numbers are attached
        files_clean = [f.split(':')[0] for f in files]
        current_bug = {
            'id': m1.group(1),
            'files': files_clean,
            'title': m1.group(3),
            'desc': ''
        }
    elif line.startswith('#### '):
        pass # Not a CH bug
    elif current_bug and line.strip() and not line.startswith('---') and not line.startswith('### '):
        current_bug['desc'] += line

    m2 = re.match(r'\|\s*([ML]-\d+)\s*\|\s*`(.*?)`\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|', line)
    if m2 and m2.group(1).startswith(('M', 'L')):
        bugs.append({
            'id': m2.group(1),
            'files': [m2.group(2).strip()],
            'title': m2.group(4).strip(),
            'desc': f'Line: {m2.group(3).strip()}'
        })

if current_bug:
    bugs.append(current_bug)

file_to_bugs = defaultdict(list)
for b in bugs:
    for f in b['files']:
        # clean backticks
        f = f.replace('`', '')
        file_to_bugs[f].append(b)

import json
with open('grouped_bugs.json', 'w') as f:
    json.dump(file_to_bugs, f, indent=2, ensure_ascii=False)

print(f"Total files to modify: {len(file_to_bugs)}")
