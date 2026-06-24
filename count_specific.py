import os
import sys

def count_lines(paths):
    src = 0
    test = 0
    for base in paths:
        for dirpath, _, filenames in os.walk(base):
            for f in filenames:
                if f.endswith('.py'):
                    fp = os.path.join(dirpath, f)
                    try:
                        with open(fp, 'r', encoding='utf-8', errors='ignore') as file:
                            lines = sum(1 for _ in file)
                    except Exception:
                        continue
                    # classify based on path components
                    if 'tests' in dirpath.split(os.sep):
                        test += lines
                    else:
                        src += lines
    return src, test

if __name__ == '__main__':
    # expecting directories: 03-development/src, tests, 03-development/tests
    dirs = ['03-development/src', 'tests', '03-development/tests']
    src, test = count_lines(dirs)
    print(f'SRC:{src} TEST:{test}')
