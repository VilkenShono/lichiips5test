#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarise distinct program coverage and per-program driver statistics from a console check."""
import argparse
import json
from pathlib import Path
import re
from collections import Counter


def read_run(path):
    programs = {}
    failures = []
    pending = None
    for line in (path / 'eden_log.txt').read_text(errors='replace').splitlines():
        if '<Error>' in line and 'CreateComputePipeline:' in line:
            failures.append(line.split('CreateComputePipeline:', 1)[1].strip())
        match = re.search(r'NX2_NIR fallback reason=(.*?) opcode=(\S+)', line)
        if match:
            pending = {'reason': match[1], 'opcode': match[2]}
        match = re.search(r'NX2_COMPILE_TIME hash=(\w+) (.*)', line)
        if match:
            row = programs.setdefault(match[1], {})
            fields = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', match[2])}
            row.update(fields)
            if 'nir_us' in fields:
                row['backend'] = 'nir'
            if 'spirv_us' in fields:
                row['backend'] = 'spirv'
                if pending:
                    row['fallback'] = pending
                    pending = None
        match = re.search(r'NX2_PIPELINE_STATS compute hash=(\w+)(.*)', line)
        if match:
            stats = {}
            for name in ('Instructions', 'VGPRs', 'LDS size', 'SGPRs', 'Scratch size'):
                value = re.search(r'\b' + name + r'=(\d+)', match[2])
                if value:
                    # search() takes allocated VGPRs, not the later Pre-Sched VGPRs.
                    stats[name] = int(value[1])
            programs.setdefault(match[1], {})['statistics'] = stats
    backends = Counter(row.get('backend', 'unknown') for row in programs.values())
    fallbacks = Counter((row['fallback']['reason'] + ':' + row['fallback']['opcode'])
                        for row in programs.values() if 'fallback' in row)
    return {'programs': programs, 'count': len(programs), 'backends': dict(backends),
            'fallbacks': dict(fallbacks), 'pipeline_failures': failures}


def compare(expanded, control, baseline):
    result = {}
    for program, row in expanded['programs'].items():
        if row.get('backend') != 'nir':
            continue
        old = baseline['programs'].get(program, {})
        other = control['programs'].get(program, {})
        left = row.get('statistics', {})
        right = other.get('statistics', {})
        comparable = all(name in left and name in right for name in ('Instructions', 'VGPRs', 'LDS size'))
        verdict = {'new_nir': old.get('backend') == 'spirv', 'baseline_available': bool(old),
                   'statistics_available': comparable}
        if comparable:
            relative = abs(left['Instructions'] - right['Instructions']) / max(1, right['Instructions'])
            verdict.update({'instruction_change_percent':
                100 * (left['Instructions'] - right['Instructions']) / max(1, right['Instructions']),
                'vgprs_equal': left['VGPRs'] == right['VGPRs'],
                'lds_equal': left['LDS size'] == right['LDS size'],
                'within_resource_gate': relative <= .005 and left['VGPRs'] == right['VGPRs'] and
                                        left['LDS size'] == right['LDS size'],
                'nir': left, 'spirv': right})
        result[program] = verdict
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    runs = {path.name: read_run(path) for path in args.evidence.iterdir()
            if path.is_dir() and (path / 'eden_log.txt').exists()}
    comparisons = {}
    for name, run in runs.items():
        if not name.startswith('expanded-'):
            continue
        suffix = name.split('-', 1)[1]
        control = runs.get('spirv-' + suffix)
        baseline = runs.get('baseline-' + suffix)
        if control and baseline:
            comparisons[name] = compare(run, control, baseline)
    result = {'runs': runs, 'comparisons': comparisons}
    (args.evidence / 'analysis.json').write_text(json.dumps(result, indent=2))
    for name, run in runs.items():
        print(name, run['count'], run['backends'], run['fallbacks'], 'pipeline failures:', len(run['pipeline_failures']))
    for name, rows in comparisons.items():
        print(name, 'new NIR:', sum(row['new_nir'] for row in rows.values()),
              'resource checks pass:', sum(row.get('within_resource_gate', False) for row in rows.values()),
              '/', len(rows))


if __name__ == '__main__':
    main()
