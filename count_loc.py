import os

def count_loc(root: str = '.'):
    src_loc = 0
    test_loc = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden directories (starting with '.') but allow current '.'
        if any(part != '.' and part.startswith('.') for part in dirpath.split(os.sep)):
            continue
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            file_path = os.path.join(dirpath, filename)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    line_count = sum(1 for _ in f)
            except Exception:
                continue
            if os.path.sep + 'tests' + os.path.sep in file_path:
                test_loc += line_count
            else:
                src_loc += line_count
    return src_loc, test_loc

if __name__ == '__main__':
    src, test = count_loc()
    print(f'SRC:{src} TEST:{test}')
