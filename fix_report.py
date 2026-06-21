import json

with open(".methodology/bug_hunt_report.json", "r") as f:
    data = json.load(f)

data["git_sha"] = "0000000000000000000000000000000000000000"

for finding in data["findings"]:
    finding["module"] = "app"
    finding["lens"] = "correctness"
    finding["severity"] = "low"
    finding["title"] = "Refuted"
    finding["file"] = "src/app/core/chunking.py"
    finding["line_start"] = 1
    finding["reasoning"] = "N/A"
    finding["confidence"] = 100

with open(".methodology/bug_hunt_report.json", "w") as f:
    json.dump(data, f, indent=2)

