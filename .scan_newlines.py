import os
root = '/Users/johnny/projects/omnibot/03-development/src'
missing_nl = []
trailing_ws = []
for dirpath, _, files in os.walk(root):
    for name in files:
        if not name.endswith('.py'):
            continue
        fp = os.path.join(dirpath, name)
        with open(fp, 'rb') as f:
            data = f.read()
        if not data:
            continue
        if not data.endswith(b'\n'):
            missing_nl.append(fp)
        text = data.decode('utf-8', errors='replace')
        for i, line in enumerate(text.splitlines(keepends=True), 1):
            core = line.rstrip('\n').rstrip('\r')
            if core != core.rstrip() or core.rstrip() + '\n' != line:
                trailing_ws.append((fp, i))
print('MISSING_NEWLINE:')
for p in missing_nl:
    print(' ', p)
print(f'COUNT_MISSING: {len(missing_nl)}')
print('TRAILING_WS:')
for p, ln in trailing_ws:
    print(f'  {p}:{ln}')
print(f'COUNT_TRAILING_WS: {len(trailing_ws)}')
