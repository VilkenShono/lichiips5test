#!/usr/bin/env python3
"""Fold a ps5-perf recording into stackcollapse lines for stacks.py: comm-tid;frame;...;leaf count.
usage: fold.py RECORDING.ps5perf MATCHED.elf > NAME.folded"""
import re, subprocess, sys, collections
PERF = '/var/home/bazzite/Projects/ps5-perf/host/ps5perf.py'
rec, elf = sys.argv[1], sys.argv[2]
out = subprocess.run([sys.executable, PERF, 'script', '-i', rec, '--sym', 'eboot.bin=' + elf], capture_output=True, text=True).stdout
stacks = collections.Counter(); comm = None; frames = []
def flush():
    if comm is not None and frames:
        stacks[';'.join([comm] + frames[::-1])] += 1
for line in out.splitlines():
    if line and not line[0].isspace():
        flush(); m = re.match(r'(\S+)\s+(\d+)/(\d+)', line); comm = f'{m.group(1)}-{m.group(3)}' if m else None; frames = []
    elif line.strip():
        m = re.match(r'\s*[0-9a-f]+\s+(.*?)\+0x[0-9a-f]+ \((.*?)\)', line)
        frames.append(m.group(1) if m else line.strip())
flush()
for k, v in stacks.items(): print(k, v)
