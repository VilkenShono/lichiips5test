#!/usr/bin/env python3
"""Summarize one experiment run directory: FPS per variant, key log lines, perf by thread."""
import sys, json, subprocess, re
from pathlib import Path
import os
PERF = os.environ.get('MKW_PS5PERF', '/var/home/bazzite/Projects/ps5-perf/host/ps5perf.py')
run = Path(sys.argv[1]).resolve()
only = sys.argv[2] if len(sys.argv) > 2 else None
for vdir in sorted(p for p in run.iterdir() if p.is_dir() and p.name != 'backup'):
    if only and vdir.name != only: continue
    s = json.loads((vdir / 'summary.json').read_text()) if (vdir / 'summary.json').exists() else {}
    print('=' * 100)
    print(vdir.name, 'perf', s.get('perf'), 'fps', s.get('fps'), 'frames', s.get('frames'), 'worst_ms', s.get('worst_ms'), 'alive', s.get('alive_at_end'))
    for w in s.get('windows', []): print('   window fps=%.2f frames=%d worst=%.0f total=%d' % (w['fps'], w['frames'], w['worst_ms'], w['total']))
    keys = (vdir / 'key-lines.txt').read_text().splitlines() if (vdir / 'key-lines.txt').exists() else []
    for l in keys:
        if any(k in l for k in ('last 600 presents', 'GPU thread split', 'Texture cache last 600', 'Texture cache: device', 'radv/ps5 submissions', 'GPU thread time', 'profile')):
            print('  ', re.sub(r'^\[\s*([\d.]+)\].*?:\d+:\w+: ', r'\1 ', l)[:300])
    heap = (vdir / 'heap.log').read_text(errors='replace') if (vdir / 'heap.log').exists() else ''
    for l in heap.splitlines():
        if l.startswith(('EDEN_ENV', 'EDEN_VULKAN_MEMORY', 'EDEN_WORKER_INHERIT')): print('  ', l[:200])
    stderr = (vdir / 'stderr.log').read_text(errors='replace') if (vdir / 'stderr.log').exists() else ''
    for l in stderr.splitlines():
        if l.startswith('EDEN_MEMORY pool'): print('  ', l[:200])
    eden = (vdir / 'eden_log.txt').read_text(errors='replace') if (vdir / 'eden_log.txt').exists() else ''
    for l in eden.splitlines():
        if 'MKW_GC' in l: last_gc = l
    try: print('   last GC:', re.sub(r'^\[\s*([\d.]+)\].*?RunGarbageCollector: ', r'\1 ', last_gc)[:250])
    except NameError: pass
    for name, extra in [('precise', ['-s', 'comm']), ('offcpu', ['-s', 'comm'])]:
        rec = vdir / (name + '.ps5perf')
        if not rec.exists(): continue
        print('--', name, 'by thread')
        out = subprocess.run([sys.executable, PERF, 'report', '-i', str(rec), '-n', '14', *extra], capture_output=True, text=True).stdout
        print('\n'.join('   ' + l for l in out.splitlines() if l.strip() and not l.startswith('#') or 'Samples' in l or 'Event count' in l))
        print('--', name, 'top symbols')
        out = subprocess.run([sys.executable, PERF, 'report', '-i', str(rec), '-n', '28', '-s', 'comm,sym'], capture_output=True, text=True).stdout
        print('\n'.join('   ' + l[:150] for l in out.splitlines() if l.strip() and not l.startswith('#')))
    stat = vdir / 'stat.log'
    if stat.exists():
        print('-- stat'); print('\n'.join('   ' + l[:150] for l in stat.read_text().splitlines()[:40]))
