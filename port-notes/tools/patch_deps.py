"""Which core patches does the PS5 port's own code depend on?

For each patch in tools/eglantine-patches: the identifiers it introduces (absent from the pinned
core), whether plain Lichii has them, and whether the port's own code (headless/, src/, tools/)
uses them. Writes a per-patch summary and a detailed report.

Usage: python3 -I patch_deps.py <port repo> <pin tree> <lichii tree> <report file>
"""
import collections
import os
import pathlib
import re
import sys

port, pin, lichii, report = map(pathlib.Path, sys.argv[1:5])
IDENT = re.compile(rb'[A-Za-z_][A-Za-z0-9_]{5,}')
SOURCE_SUFFIXES = {'.h', '.hpp', '.cpp', '.c', '.cc', '.inc', '.cmake', '.txt', '.py', '.sh', '.glsl', '.vert', '.frag', '.comp'}


def identifiers_in_tree(root, subdirs, skip=()):
    found = set()
    for sub in subdirs:
        base = root / sub
        if not base.exists():
            continue
        for directory, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ('.git', '.cache') and os.path.join(directory, d) not in skip]
            for name in files:
                path = pathlib.Path(directory) / name
                if path.suffix not in SOURCE_SUFFIXES or path.is_symlink():
                    continue
                try:
                    found.update(IDENT.findall(path.read_bytes()))
                except OSError:
                    pass
    return found


def identifiers_by_file(root, subdirs, skip=()):
    where = collections.defaultdict(set)
    for sub in subdirs:
        base = root / sub
        for directory, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if os.path.join(directory, d) not in skip]
            for name in files:
                path = pathlib.Path(directory) / name
                if path.suffix not in SOURCE_SUFFIXES:
                    continue
                for ident in set(IDENT.findall(path.read_bytes())):
                    where[ident].add(str(path.relative_to(root)))
    return where


pin_ids = identifiers_in_tree(pin, ['src', 'externals'])
lichii_ids = identifiers_in_tree(lichii, ['src', 'externals'])
port_ids = identifiers_by_file(port, ['headless', 'src', 'tools'], skip=(str(port / 'tools/eglantine-patches'),))
lines = []
summary = []
for patch in sorted((port / 'tools/eglantine-patches').glob('*.patch')):
    added = set()
    new_files = []
    previous = b''
    for line in patch.read_bytes().splitlines():
        if line.startswith(b'+++ b/') and previous.startswith(b'--- /dev/null'):
            new_files.append(line[6:].decode())
        if line.startswith(b'+') and not line.startswith(b'+++'):
            added.update(IDENT.findall(line[1:]))
        previous = line
    introduced = added - pin_ids
    used = sorted(i for i in introduced if i in port_ids)
    used_missing = [i for i in used if i not in lichii_ids]
    used_present = [i for i in used if i in lichii_ids]
    summary.append(f"{patch.stem:48s} introduces {len(introduced):4d}  port uses {len(used):3d}  (absent in Lichii: {len(used_missing):3d})  new files: {len(new_files)}")
    lines.append(f"== {patch.stem}")
    for ident in used_missing:
        files = sorted(port_ids[ident])
        lines.append(f"   NEED  {ident.decode():50s} {', '.join(files[:4])}{' ...' if len(files) > 4 else ''}")
    for ident in used_present:
        files = sorted(port_ids[ident])
        lines.append(f"   have  {ident.decode():50s} {', '.join(files[:3])}{' ...' if len(files) > 3 else ''}")
report.write_text('\n'.join(lines) + '\n')
print('\n'.join(summary))
