#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Qualify opt-in native MME dispatch against the JIT on Mario Kart World.

Reuse the cache qualification runner's console lease, executable verification,
private save backup and restoration. Keep game files/bytecode on the console.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

helper = Path(__file__).with_name('check-pipeline-cache-console.py')
spec = importlib.util.spec_from_file_location('cache_console', helper)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    for key in ('candidate', 'elf', 'launcher', 'out'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=90)
    parser.add_argument('--resolution', choices=('0.5x', '0.75x', '1x'), default='0.5x')
    args = parser.parse_args()
    if os.environ.get('EGLANTINE_CONSOLE_LEASE_HOST') != args.host:
        subprocess.run([sys.executable, str(Path(__file__).with_name('console-lease.py')),
                        '--host', args.host, '--owner', 'native-mme-check', 'run', '--wait', '--',
                        sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], check=True)
        return
    console = base.CacheConsole(args)
    results = []
    try:
        console.initialize()
        for label, mode in [('jit-a', '0'), ('check', 'check'), ('native-a', '1'), ('jit-b', '0'), ('native-b', '1')]:
            console.put(console.app + '/env.txt',
                        ('EDEN_NX2_MME_NATIVE=' + mode + '\nEDEN_NX2_MME_BENCH=' + str(int(mode != 'check')) + '\nEDEN_LOG_FILTER=*:Warning Render.Vulkan:Info\n').encode())
            result = console.run_cache(label)
            logs = (console.out / label / 'eden_log.txt').read_text(errors='replace')
            stderr = (console.out / label / 'stderr.log').read_text(errors='replace')
            failures = ('Native MME (JIT) failed:', 'Native MME (JIT, split front) failed:',
                        'Native MME failed:', 'VK_ERROR_OUT_OF_DEVICE_MEMORY', 'VK_ERROR_DEVICE_LOST')
            if any(failure in logs + stderr for failure in failures):
                raise RuntimeError(label + ': macro execution or graphics device failure; inspect collected logs')
            if any('MME native' in line and 'mismatch=' in line for line in logs.splitlines()):
                raise RuntimeError('Native/interpreter mismatch; retain logs and leave native dispatch disabled')
            markers = [line for line in logs.splitlines() if 'MME native ' in line]
            if mode == 'check':
                if not any('MME native check ' in line for line in markers):
                    raise RuntimeError('No matching macros were checked in this workload')
                if any(int(count) != 0 for count in re.findall(r'differences=(\d+)', '\n'.join(markers))):
                    raise RuntimeError('Native/interpreter differences reported')
            if mode == '1' and not any('MME native run ' in line for line in markers):
                raise RuntimeError('No native macro replacement ran in this workload')
            counters = {}
            for path, kind, calls, total, emit, own, writes in re.findall(
                    r'MME_BENCH path=(\w+) id=(\d+) calls=(\d+) total_ticks=(\d+) emit_ticks=(\d+) own_ticks=(\d+) writes=(\d+)', logs):
                counters[path + ':' + kind] = dict(calls=int(calls), total_ticks=int(total),
                    emit_ticks=int(emit), own_ticks=int(own), writes=int(writes))
            result['bench_counters'] = counters
            if mode != 'check' and not counters:
                raise RuntimeError('No warmed macro benchmark samples were collected')
            result['mme_lines'] = markers
            results.append(result)
            (console.out / 'results.json').write_text(json.dumps(results, indent=2))
        (console.out / 'verification.json').write_text(json.dumps({
            'jit_check_native_rendered': True, 'native_replacements_executed': True,
            'sampled_interpreter_differences': 0, 'default_enabled': False}, indent=2))
    finally:
        console.restore()


if __name__ == '__main__':
    main()
