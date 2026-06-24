import os
import re

# Fix N814
path1 = "03-development/tests/unit/test_aee_adapter_mutation_kills.py"
with open(path1, "r") as f:
    content = f.read()
content = content.replace("from app.services.aee.adapter import ActionAdapter as _AA", "from app.services.aee.adapter import ActionAdapter")
content = re.sub(r'\b_AA\b', 'ActionAdapter', content)
with open(path1, "w") as f:
    f.write(content)

# Fix E702
path2 = "03-development/tests/test_coverage_supplementary2.py"
with open(path2, "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if ";" in line:
        match = re.match(r'^(\s+)', line)
        indent = match.group(1) if match else ""
        parts = line.split(";")
        for i, part in enumerate(parts):
            clean = part.strip()
            if not clean:
                continue
            
            # if it's the last part and original line has \n, keep \n
            new_lines.append(indent + clean + '\n')
    else:
        new_lines.append(line)

with open(path2, "w") as f:
    f.writelines(new_lines)

