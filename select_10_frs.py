import subprocess
import re
import random

total_frs = {f"FR-{i:02d}" for i in range(1, 109)}
completed_frs = set()

r = subprocess.run(["git", "log", "--oneline"], capture_output=True, text=True)

for line in r.stdout.splitlines():
    m = re.search(r'(?:feat|refactor)\(FR-(\d+)\):\s*(?:GREEN|IMPROVE)', line)
    if m:
        completed_frs.add(f"FR-{int(m.group(1)):02d}")

completed_list = sorted(list(completed_frs))
random.seed(42) # fixed seed for reproducibility across agent restarts if needed, or I can use system time
selected = random.sample(completed_list, 10)
print(f"Selected 10 FRs: {selected}")
