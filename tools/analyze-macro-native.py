#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize repeated in-game macro dispatch samples; never infer an FPS gain."""
from pathlib import Path
import argparse
import json
import re
import statistics

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('run', type=Path)
args = parser.parse_args()
rows = []
for entry in json.loads((args.run / 'results.json').read_text()):
    label = entry['label']
    if label == 'check':
        continue
    eden = (args.run / label / 'eden_log.txt').read_text(errors='replace')
    heap = (args.run / label / 'heap.log').read_text(errors='replace')
    samples = {}
    history = {}
    pattern = r'MME_BENCH path=(\w+) id=(\d+) calls=(\d+) total_ticks=(\d+) emit_ticks=(\d+) own_ticks=(\d+) writes=(\d+) tsc_hz=(\d+)'
    for line in eden.splitlines():
        match = re.search(pattern, line)
        if not match:
            continue
        path, kind, calls, total, emit, own, writes, hz = match.groups()
        stamp = re.match(r'\[\s*([\d.]+)\]', line)
        values = {key: int(value) for key, value in
            zip(('calls', 'total', 'emit', 'own', 'writes', 'hz'), (calls, total, emit, own, writes, hz))}
        history.setdefault(path + ':' + kind, []).append((float(stamp[1]) if stamp else None, values))
    for key, records in history.items():
        end_time, end = records[-1]
        start = next(((t, values) for t, values in records
                      if t is not None and end_time is not None and t >= end_time - 20), None)
        if start and end['calls'] > start[1]['calls']:
            samples[key] = {name: end[name] - start[1][name] for name in ('calls', 'total', 'emit', 'own', 'writes')}
            samples[key].update(hz=end['hz'], window_seconds=end_time - start[0])
        else:
            samples[key] = dict(end, window_seconds=None)
    fps = [float(value) for value in re.findall(r'EDEN_VULKAN_FRAME .*?fps=([\d.]+)', heap)]
    row = {'run': label, 'mode': 'jit' if label.startswith('jit') else 'native', 'macros': {},
           'fps_last_windows': fps[-5:], 'fps_median_last_windows': statistics.median(fps[-5:]) if fps else None}
    for key, sample in samples.items():
        count = sample['calls']
        if sample['own'] != sample['total'] - sample['emit'] or sample['own'] > sample['total']:
            raise RuntimeError(label + ': invalid nested timing accounting for ' + key)
        row['macros'][key] = {'calls': count, 'own_ticks_per_call': sample['own'] / count, 'window_seconds': sample['window_seconds'],
                              'total_ticks_per_call': sample['total'] / count,
                              'writes_per_call': sample['writes'] / count,
                              'own_ns_per_call': sample['own'] * 1e9 / sample['hz'] / count if sample['hz'] else None}
    rows.append(row)
comparisons = []
keys = sorted(set.intersection(*(set(row['macros']) for row in rows))) if rows else []
for key in keys:
    baseline = [row['macros'][key] for row in rows if row['mode'] == 'jit']
    native = [row['macros'][key] for row in rows if row['mode'] == 'native']
    if len(baseline) < 2 or len(native) < 2:
        continue
    old = statistics.median(value['own_ticks_per_call'] for value in baseline)
    new = statistics.median(value['own_ticks_per_call'] for value in native)
    old_writes = statistics.median(value['writes_per_call'] for value in baseline)
    new_writes = statistics.median(value['writes_per_call'] for value in native)
    comparisons.append({'macro': key, 'jit_own_ticks_median': old, 'native_own_ticks_median': new,
                        'own_ticks_reduction_percent': 100 * (old - new) / old if old else None,
                        'jit_own_ticks_range': [min(v['own_ticks_per_call'] for v in baseline), max(v['own_ticks_per_call'] for v in baseline)],
                        'native_own_ticks_range': [min(v['own_ticks_per_call'] for v in native), max(v['own_ticks_per_call'] for v in native)],
                        'jit_writes_per_call': old_writes, 'native_writes_per_call': new_writes,
                        'similar_write_mix': abs(old_writes - new_writes) <= max(0.02, old_writes * 0.02)})
result = {'runs': rows, 'comparisons': comparisons,
          'limits': 'Timestamp-counter estimates with equal instrumentation, first 1024 calls excluded; late ~20-second counter deltas where available; engine method writes subtracted. Interruptions/preemption remain. Attract scenes and shader progress vary: these FPS windows do not establish a controlled FPS gain.'}
(args.run / 'performance.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
