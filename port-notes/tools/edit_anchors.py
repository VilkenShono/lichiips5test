"""Applies anchor edits to tools/prepare-vulkan-port.py by position, so long tuples need no retyping.

Usage: python3 -I edit_anchors.py <script> <spec.py>

spec.py defines EDITS: {(relative file, index): value}. index counts the (old, new) tuples of
that file's adapt() calls in script order, as tools/anchor_report.py numbers them. value is:
  None                 delete the tuple (and the comment lines directly above it)
  (old, new)           replace both strings
  ('KEEP', new)        keep the old string, replace the new one
  (old, 'KEEP')        replace the old string, keep the new one (source expression kept)
  'raw python source'  replace the whole tuple with this source
INSERT_AFTER: {(relative file, index): [(old, new), ...]} adds tuples after one (optional).
"""
import ast
import pathlib
import sys

script = pathlib.Path(sys.argv[1])
spec = {}
exec(compile(pathlib.Path(sys.argv[2]).read_text(), sys.argv[2], 'exec'), spec)
edits = dict(spec.get('EDITS', {}))
inserts = dict(spec.get('INSERT_AFTER', {}))
text = script.read_text()
lines = text.split('\n')
starts = [0]
for line in lines:
    starts.append(starts[-1] + len(line) + 1)


def offset(lineno, col):
    # ast columns are UTF-8 byte offsets; convert through the line's bytes.
    line = lines[lineno - 1]
    return starts[lineno - 1] + len(line.encode()[:col].decode())


def literal(value):
    if '\n' in value and "'''" not in value and not value.endswith("'") and '\\' not in value:
        return "'''" + value + "'''"
    return repr(value)


counters = {}
operations = []  # (start, end, replacement)
for node in ast.walk(ast.parse(text)):
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'adapt'):
        continue
    if not (node.args and isinstance(node.args[0], ast.Constant) and len(node.args) >= 3 and isinstance(node.args[2], ast.List)):
        continue
    node._order = (node.lineno, node.col_offset)
calls = sorted((n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == 'adapt' and n.args and isinstance(n.args[0], ast.Constant)
                and len(n.args) >= 3 and isinstance(n.args[2], ast.List)), key=lambda n: (n.lineno, n.col_offset))
used = set()
for call in calls:
    relative = call.args[0].value
    for element in call.args[2].elts:
        index = counters.get(relative, 0)
        counters[relative] = index + 1
        key = (relative, index)
        begin, end = offset(element.lineno, element.col_offset), offset(element.end_lineno, element.end_col_offset)
        if key in inserts:
            addition = ''.join(f",\n    ({literal(old)},\n     {literal(new)})" for old, new in inserts[key])
            operations.append((end, end, addition))
            used.add(('insert', key))
        if key not in edits:
            continue
        used.add(key)
        value = edits[key]
        if value is None:
            # Whole lines: from the first comment line directly above to the end of the tuple's line.
            first = element.lineno
            if lines[first - 1][:element.col_offset].strip():
                raise SystemExit(f"{key}: tuple does not start its line; delete it by hand")
            while first > 1 and lines[first - 2].lstrip().startswith('#'):
                first -= 1
            tail = lines[element.end_lineno - 1][element.end_col_offset:].strip()
            if tail not in (',', ''):
                raise SystemExit(f"{key}: text follows the tuple on its line ({tail!r}); delete it by hand")
            operations.append((starts[first - 1], starts[element.end_lineno], ''))
        elif isinstance(value, str):
            operations.append((begin, end, value))
        else:
            old, new = value
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                raise SystemExit(f"{key}: not a two-element tuple")
            old_node, new_node = element.elts
            old_source = text[offset(old_node.lineno, old_node.col_offset):offset(old_node.end_lineno, old_node.end_col_offset)]
            new_source = text[offset(new_node.lineno, new_node.col_offset):offset(new_node.end_lineno, new_node.end_col_offset)]
            old_text = old_source if old == 'KEEP' else literal(old)
            new_text = new_source if new == 'KEEP' else literal(new)
            operations.append((begin, end, f"({old_text},\n     {new_text})"))
missing = [key for key in edits if key not in used] + [key for key in inserts if ('insert', key) not in used]
if missing:
    raise SystemExit(f"no such anchors: {missing}")
for begin, end, replacement in sorted(operations, key=lambda op: (op[0], op[1]), reverse=True):
    text = text[:begin] + replacement + text[end:]
ast.parse(text)
script.write_text(text)
print(f"applied {len(operations)} edits to {script.name}")
