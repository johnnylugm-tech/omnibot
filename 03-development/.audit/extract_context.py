import re
import os

def main():
    report_path = "/Users/johnny/projects/omnibot/03-development/.audit/bug-report-2026-06-22.md"
    base_dir = "/Users/johnny/projects/omnibot"
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match P0, P1 bugs which have format:
    # ### BUG-XX ...
    # **File**: `path:lines`
    bug_pattern = re.compile(r"(BUG-\d+|M-\d+).*?(?:\n.*?)*?\*\*File\*\*: `([^`]+)`", re.MULTILINE)
    
    # Wait, the P2 table format is:
    # | M-01 | dst | `dst.py:451-459` | ...
    
    # Let's extract manually:
    bugs = []
    
    # Extract P0/P1
    for match in re.finditer(r"### (BUG-\d+)[^\n]*\n\n\*\*File\*\*: `([^`]+)`", content):
        bugs.append((match.group(1), match.group(2)))
    
    for match in re.finditer(r"\*\*?(BUG-\d+)[^\n]*\*\*?.*?\n`([^`]+)`", content):
        if (match.group(1), match.group(2)) not in bugs:
            bugs.append((match.group(1), match.group(2)))
            
    # Extract P2 table
    for match in re.finditer(r"\|\s*(M-\d+)\s*\|\s*[^\|]*\s*\|\s*`([^`]+)`", content):
        bugs.append((match.group(1), match.group(2)))
        
    print(f"Found {len(bugs)} bugs to extract context for.")
    
    def parse_lines(line_str):
        # e.g., "177-205", "656, 578", "27, 68-73"
        lines = []
        parts = line_str.split(",")
        for p in parts:
            p = p.strip()
            if "-" in p:
                s, e = p.split("-")
                lines.extend(list(range(int(s), int(e)+1)))
            else:
                lines.append(int(p))
        return lines

    for bug_id, file_ref in bugs:
        print(f"\n{'='*40}\nEvaluating: {bug_id} ({file_ref})\n{'='*40}")
        if ":" in file_ref:
            file_path, lines_str = file_ref.split(":", 1)
        else:
            file_path = file_ref
            lines_str = ""
            
        # Try to resolve full path
        # In the markdown, it's sometimes "03-development/src/app/core/paladin.py"
        # Sometimes just "auth.py" or "dst.py"
        full_path = ""
        if file_path.startswith("03-development/"):
            full_path = os.path.join(base_dir, file_path)
        else:
            # find the file using os.walk
            for root, dirs, files in os.walk(os.path.join(base_dir, "03-development/src")):
                if file_path in files:
                    full_path = os.path.join(root, file_path)
                    break
                    
        if not full_path or not os.path.exists(full_path):
            print(f"File not found: {file_path}")
            continue
            
        with open(full_path, "r", encoding="utf-8") as f:
            file_lines = f.readlines()
            
        target_lines = parse_lines(lines_str) if lines_str else []
        
        if not target_lines:
            print("No specific lines mentioned.")
            continue
            
        min_line = max(1, min(target_lines) - 5)
        max_line = min(len(file_lines), max(target_lines) + 5)
        
        for i in range(min_line, max_line + 1):
            marker = ">> " if i in target_lines else "   "
            print(f"{marker}{i}: {file_lines[i-1].rstrip()}")

if __name__ == '__main__':
    main()
