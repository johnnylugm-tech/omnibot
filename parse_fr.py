import subprocess
import re

total_frs = {f"FR-{i:02d}" for i in range(1, 109)} # FR-01 to FR-108
completed_frs = set()

r = subprocess.run(["git", "log", "--oneline"], capture_output=True, text=True)

for line in r.stdout.splitlines():
    m = re.search(r'(?:feat|refactor)\(FR-(\d+)\):\s*(?:GREEN|IMPROVE)', line)
    if m:
        completed_frs.add(f"FR-{int(m.group(1)):02d}")

print(f"Total FRs: {len(total_frs)}")
print(f"Completed FRs in Phase 3: {len(completed_frs)}")
uncompleted = sorted(list(total_frs - completed_frs), key=lambda x: int(x.split('-')[1]))
print(f"Uncompleted FRs ({len(uncompleted)}): {uncompleted}")
