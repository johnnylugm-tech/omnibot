import json
import subprocess
import time
import sys

with open('grouped_bugs.json') as f:
    file_to_bugs = json.load(f)

total = len(file_to_bugs)
success = 0

for i, (file_path, bugs) in enumerate(file_to_bugs.items(), 1):
    print(f"[{i}/{total}] Fixing bugs in {file_path}...")
    
    prompt = f"You are tasked with fixing {len(bugs)} bugs in the file `{file_path}`.\n\n"
    prompt += "Bug details:\n"
    for b in bugs:
        prompt += f"- [{b['id']}] {b['title']}:\n  {b['desc']}\n\n"
    prompt += "Instructions:\n"
    prompt += "1. Use the Edit tool to modify the file directly.\n"
    prompt += "2. Provide a correct and complete solution for each bug. Do NOT use workarounds or simple bypasses.\n"
    prompt += "3. If the bug involves missing imports, add them.\n"
    prompt += "4. When you are done, output a brief summary of what was fixed.\n"
    
    try:
        # We use Claude CLI to do the edit
        result = subprocess.run(
            ["claude", "--permission-mode", "bypassPermissions", "-p", prompt],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"Successfully fixed {file_path}.")
        success += 1
    except subprocess.CalledProcessError as e:
        print(f"Error fixing {file_path}. Claude exited with code {e.returncode}.")
        print(f"Stderr: {e.stderr}")
        print(f"Stdout: {e.stdout}")

print(f"\nDone! Successfully attempted fixes for {success}/{total} files.")
