"""Do anchors that still match land in the same place?

Usage: python3 -I context_check.py <anchors.json> <pin tree> <lichii tree>

For each anchor that matches exactly once in both trees: the enclosing top-level definition (the
nearest earlier line starting at column 0 with an identifier) in each tree, and the two lines on
each side of the match. Prints anchors whose enclosing definition differs, and those whose
neighbouring lines all differ.
"""
import json
import pathlib
import re
import sys

data = json.load(open(sys.argv[1]))
pin, lichii = pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
HEAD = re.compile(r'^[A-Za-z_]')
NAME = re.compile(r'([A-Za-z_~][A-Za-z0-9_:<>~]*)\s*\(')


def enclosing(text, position):
    lines = text[:position].split('\n')
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if HEAD.match(line) and not line.startswith(('template', 'namespace', 'using', 'extern', 'static_assert', 'constexpr', 'inline constexpr')):
            match = NAME.search(line)
            return (match.group(1) if match else line.strip()[:60])
    return '<top>'


def neighbours(text, start, end):
    before = [l.strip() for l in text[:start].split('\n')[-4:-1] if l.strip()][-2:]
    after = [l.strip() for l in text[end:].split('\n')[1:4] if l.strip()][:2]
    return before, after


flagged = unchecked = same = 0
for anchor in data['anchors']:
    relative, old = anchor['file'], anchor['old']
    a_path, b_path = pin / relative, lichii / relative
    if not a_path.exists() or not b_path.exists():
        continue
    a, b = a_path.read_text(), b_path.read_text()
    if a.count(old) != 1 or b.count(old) != 1:
        unchecked += 1
        continue
    pa, pb = a.index(old), b.index(old)
    ea, eb = enclosing(a, pa), enclosing(b, pb)
    na, nb = neighbours(a, pa, pa + len(old)), neighbours(b, pb, pb + len(old))
    context_same = bool(set(na[0]) & set(nb[0])) or bool(set(na[1]) & set(nb[1]))
    if ea != eb or not context_same:
        flagged += 1
        kind = 'ENCLOSING' if ea != eb else 'context'
        print(f"--- {kind}: [{relative.split('/')[-1]} #{anchor['index']}] script line {anchor['line']}")
        print(f"    anchor: {old.strip().splitlines()[0][:110]}")
        print(f"    pin:    in {ea}   lichii: in {eb}  (line {b.count(chr(10), 0, pb) + 1})")
    else:
        same += 1
print(f"\n{same} anchors in the same place, {flagged} flagged, {unchecked} not comparable (re-anchored or chained)")
