"""locate.py <anchors.json> <core tree> <file substring> [#index ...]
For each broken anchor: which of its lines still exist in the target file (line numbers), which do not."""
import json, sys, pathlib
data = json.load(open(sys.argv[1])); core = pathlib.Path(sys.argv[2]); sub = sys.argv[3]
only = {int(a[1:]) for a in sys.argv[4:] if a.startswith('#')}
cache = {}
for a in data['anchors']:
    if sub not in a['file'] or a['count'] == 1 or (only and a['index'] not in only):
        continue
    lines = cache.setdefault(a['file'], (core / a['file']).read_text().split('\n'))
    index = {}
    for n, l in enumerate(lines, 1):
        index.setdefault(l.strip(), []).append(n)
    print(f"=== [{a['file'].split('/')[-1]} #{a['index']}] script line {a['line']} matches={a['count']}")
    for l in a['old'].split('\n'):
        s = l.strip()
        if not s:
            continue
        hits = index.get(s, [])
        mark = ('@' + ','.join(map(str, hits[:4])) + ('+' if len(hits) > 4 else '')) if hits else 'MISSING'
        print(f"  {mark:>16s} | {l[:150]}")
