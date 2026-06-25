import json
import os

with open("mi_output_hash.json") as f:
    hash_out = json.load(f)

hash_bases = {os.path.basename(k): v for k, v in hash_out.items()}

import subprocess
out = subprocess.run(["radon", "mi", ".", "-j"], capture_output=True, text=True)
orig = json.loads(out.stdout)

deltas = []
for k in orig:
    base = os.path.basename(k)
    if base in hash_bases:
        o = orig[k]["mi"]
        n = hash_bases[base]["mi"]
        deltas.append(n - o)
        if "auth.py" in k or "ab_testing" in k or "a2a.py" in k or "webui.py" in k:
            print(f"{k}: Orig {o:.2f}, New {n:.2f}, Delta {n-o:.2f}")

print(f"Mean Original: {sum(orig[k]['mi'] for k in orig)/len(orig):.2f}")
print(f"Mean Hash: {sum(hash_bases[os.path.basename(k)]['mi'] for k in orig if os.path.basename(k) in hash_bases)/len(deltas):.2f}")
print(f"Mean Delta: {sum(deltas)/len(deltas):.2f}")
