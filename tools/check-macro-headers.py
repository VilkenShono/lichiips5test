#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify all compiled MacroEngine consumers use the same generated layout."""
from pathlib import Path
import subprocess
import json
import shlex
import sys

build = Path(sys.argv[1]).resolve()
expected = build / 'headless/macro-native/video_core/macro.h'
if not expected.is_file():
    raise SystemExit('Missing native MME header override')
active = set()
for entry in json.loads((build / 'compile_commands.json').read_text()):
    arguments = shlex.split(entry['command'])
    if '-o' in arguments:
        output = Path(arguments[arguments.index('-o') + 1])
        active.add((Path(entry['directory']) / output).resolve())
process = subprocess.Popen(['ninja', '-C', str(build), '-t', 'deps'], stdout=subprocess.PIPE, text=True)
count = 0
wrong = []
current = ''
selected = False
for line in process.stdout:
    if line and not line[0].isspace():
        current = line.rstrip()
        selected = (build / line.split(': #deps', 1)[0]).resolve() in active
    path = line.strip()
    if selected and path.endswith('/video_core/macro.h'):
        count += 1
        if Path(path).resolve() != expected:
            wrong.append(current + ': ' + path)
if process.wait() != 0:
    raise SystemExit('Ninja dependency inspection failed')
if wrong or count == 0:
    raise SystemExit('Mixed MacroEngine layouts: ' + '\n'.join(wrong[:20]) if wrong else 'No compiled MacroEngine consumers')
print(f'PASS native MME header layout: all {count} compiled consumers use the generated override')
