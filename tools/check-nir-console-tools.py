#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline regressions for executable verification and console-evidence interpretation."""
import importlib.util
from pathlib import Path
import struct
import tempfile

root = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), root / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runner = module('check-nir-console')
analyzer = module('analyze-nir-console')
blob = bytearray(256)
blob[:6] = b'\x7fELF\x02\x01'
struct.pack_into('<HH', blob, 16, 3, 62)
struct.pack_into('<Q', blob, 24, 0x4000)
struct.pack_into('<Q', blob, 32, 64)
struct.pack_into('<HH', blob, 54, 56, 1)
struct.pack_into('<IIQQQQQQ', blob, 64, 1, 5, 128, 0x4000, 0, 4, 8, 16)
blob[128:132] = b'code'
expected = runner.load_segments(bytes(blob))
metadata = blob.copy()
metadata[255] ^= 0xff
assert runner.load_segments(bytes(metadata)) == expected
modified = blob.copy()
modified[128] ^= 0xff
assert runner.load_segments(bytes(modified)) != expected
entry = blob.copy()
struct.pack_into('<Q', entry, 24, 0x4001)
assert runner.load_segments(bytes(entry)) != expected
for invalid in (b'bad', bytes(blob[:129]), bytes(bytearray(64))):
    try:
        runner.load_segments(invalid)
    except (ValueError, struct.error):
        pass
    else:
        raise AssertionError('Invalid executable accepted')

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp)
    (path / 'eden_log.txt').write_text('''NX2_COMPILE_TIME hash=abcd nir_us=8
NX2_COMPILE_TIME hash=abcd driver_us=9
NX2_COMPILE_TIME hash=abcd driver_us=9
NX2_PIPELINE_STATS compute hash=abcd Instructions=1000 VGPRs=128 LDS size=1024 Pre-Sched VGPRs=100
NX2_NIR fallback reason=opcode opcode=MissingOp
NX2_COMPILE_TIME hash=dcba spirv_us=4
''')
    run = analyzer.read_run(path)
    assert run['count'] == 2 and run['backends'] == {'nir': 1, 'spirv': 1}
    assert run['programs']['abcd']['statistics']['VGPRs'] == 128
    assert run['fallbacks'] == {'opcode:MissingOp': 1}
    baseline = {'programs': {'abcd': {'backend': 'spirv'}}}
    control = {'programs': {'abcd': {'statistics': {'Instructions': 1000, 'VGPRs': 128, 'LDS size': 1024}}}}
    row = analyzer.compare(run, control, baseline)['abcd']
    assert row['new_nir'] and row['within_resource_gate']
    control['programs']['abcd']['statistics']['VGPRs'] = 129
    assert not analyzer.compare(run, control, baseline)['abcd']['within_resource_gate']
    missing = analyzer.compare(run, {'programs': {}}, {'programs': {}})['abcd']
    assert not missing['statistics_available'] and not missing['new_nir']

print('NIR console tools: load-segment/entry integrity, metadata handling, log deduplication, allocated registers and incomplete evidence PASS')
