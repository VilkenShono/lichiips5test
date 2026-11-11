"""show.py <anchors.json> [file substring] [--all] [--full]: prints broken anchors (old text) with script lines."""
import json, sys
data = json.load(open(sys.argv[1]))
sub = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else ''
show_all, full = '--all' in sys.argv, '--full' in sys.argv
for a in data['anchors']:
    if sub not in a['file'] or (a['count'] == 1 and not show_all):
        continue
    old = a['old'] if full else a['old'][:400]
    print(f"--- [{a['file'].split('/')[-1]} #{a['index']}] script line {a['line']}  matches={a['count']}")
    print(old)
