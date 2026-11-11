"""Runs tools/prepare-vulkan-port.py statement by statement in --report mode, so one failing
custom step does not hide the rest. Prints: anchors tried, anchors broken (by file), other failures.

Usage: python3 -I anchor_report.py <prepare-vulkan-port.py> <core source> <output dir> [--list]
"""
import ast
import collections
import json
import pathlib
import sys

details = []
current_line = [0]
script, source, output = sys.argv[1:4]
verbose = '--list' in sys.argv
text = open(script).read()
tree = ast.parse(text)
sys.argv = [script, '--report', source, output]
ns = {'__name__': '__main__', '__file__': script}
tried = collections.Counter()
other = []
for node in tree.body:
    code = compile(ast.Module([node], []), script, 'exec')
    current_line[0] = node.lineno
    try:
        exec(code, ns)
    except SystemExit:
        pass
    except Exception as error:  # noqa: BLE001 - report everything
        other.append((node.lineno, f"{type(error).__name__}: {str(error)[:150]}"))
    if isinstance(node, ast.FunctionDef) and node.name == 'adapt':
        # Re-define adapt with a recording line before its match test (counts are sequential:
        # each anchor is tested against the text the earlier replacements left).
        segment = ast.get_source_segment(text, node)
        marker = "        if text.count(old) != 1:"
        assert segment.count(marker) == 1
        segment = segment.replace(marker, "        __record(relative, old, new, text.count(old))\n" + marker)
        exec(compile(segment, script, 'exec'), ns)

        def record(relative, old, new, count):
            tried[relative] += 1
            details.append({'file': relative, 'index': tried[relative] - 1, 'old': old, 'new': new,
                            'line': current_line[0], 'count': count})

        ns['__record'] = record
broken = ns.get('broken', [])
by_file = collections.Counter(line.split(': ', 1)[0] for line in broken)
print(f"anchors tried: {sum(tried.values())} in {len(tried)} files")
print(f"anchors broken: {len(broken)} in {len(by_file)} files")
print(f"other failing steps: {len(other)}")
for lineno, message in other:
    print(f"  line {lineno}: {message}")
print("broken by file:")
for name, count in by_file.most_common():
    print(f"  {count:3d}/{tried[name]:3d}  {name}")
pathlib.Path(output, 'anchors.json').write_text(json.dumps({'anchors': details, 'other': other}))
if verbose:
    for line in broken:
        print("  " + line[:230])
