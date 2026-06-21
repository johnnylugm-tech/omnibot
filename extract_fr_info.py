import json
import subprocess
import re
import os

selected = ['FR-81', 'FR-104', 'FR-04', 'FR-28', 'FR-24', 'FR-21', 'FR-107', 'FR-103', 'FR-91', 'FR-64']

# 1. Get module mapping
with open('.methodology/SAB.json') as f:
    sab = json.load(f)
fr_module = sab.get('fr_module_traceability', {})

info = {}
for fr in selected:
    info[fr] = {"module": fr_module.get(fr), "spec": "", "test_spec": "", "code": ""}

# 2. Extract from SRS.md, SAD.md, TEST_SPEC.md
def extract_section(filepath, frs):
    if not os.path.exists(filepath): return {}
    content = open(filepath).read()
    res = {fr: [] for fr in frs}
    for fr in frs:
        # naive grep-like extraction around the FR
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if fr in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 15)
                res[fr].append("\n".join(lines[start:end]))
    return res

srs_data = extract_section("01-requirements/SRS.md", selected)
sad_data = extract_section("02-architecture/SAD.md", selected)
test_data = extract_section("02-architecture/TEST_SPEC.md", selected)

for fr in selected:
    info[fr]["spec"] = "\n---\n".join(srs_data.get(fr, []) + sad_data.get(fr, []))
    info[fr]["test_spec"] = "\n---\n".join(test_data.get(fr, []))

# 3. Extract the implementation
for fr in selected:
    mod = info[fr]["module"]
    if mod:
        # e.g., app.infra.redis_streams -> src/app/infra/redis_streams.py or similar
        filepath = "03-development/src/" + mod.replace(".", "/") + ".py"
        if not os.path.exists(filepath):
            filepath = "03-development/" + mod.replace(".", "/") + ".py"
        
        if os.path.exists(filepath):
            info[fr]["code"] = open(filepath).read()
        
        testpath = "03-development/tests/test_" + fr.lower().replace("-", "") + ".py"
        if os.path.exists(testpath):
            info[fr]["code"] += "\n\n# TESTS\n" + open(testpath).read()

with open("fr_audit_data.json", "w") as f:
    json.dump(info, f, indent=2)

print("Extraction complete. Check fr_audit_data.json")
