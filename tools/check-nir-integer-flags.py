#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the production NIR integer flags using the pinned Mesa's host libraries.

MESA_HOST_BUILD may name a matching host Mesa build. Defaults to the RADV CLC host build.
No Mesa source or build is modified by this check.
"""
import ctypes.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
build = Path(os.environ.get('MESA_HOST_BUILD', root.parent / 'mihawk-vulkan-review/.deps/work/radv-clc-build')).resolve()
commands = json.loads((build / 'compile_commands.json').read_text())
entry = next(c for c in commands if c['file'].endswith('/nir/nir.c'))
args = shlex.split(entry['command'])
includes = [a for a in args if a.startswith(('-I', '-D'))]
archives = [build / p for p in ('src/compiler/nir/libnir.a', 'src/compiler/libcompiler.a',
    'src/util/libmesa_util.a', 'src/util/libmesa_util_simd.a',
    'src/util/libmesa_util_clflush.a', 'src/util/libmesa_util_clflushopt.a',
    'src/util/blake3/libblake3.a', 'src/c11/impl/libmesa_util_c11.a')]
cache = Path((root / '.local/headless-cache').read_text().strip())
boost_includes = list((cache / 'source/.cache/cpm/boost').glob('*/libs/*/include'))
fmt = root / '.deps/fmt-12.1.0/include'
with tempfile.TemporaryDirectory(prefix='eden-nir-ops-') as tmp:
    for source in ('check-nir-integer-flags.cpp', 'check-nir-compute-ops.cpp', 'check-nir-ir-flags.cpp'):
        exe = Path(tmp) / Path(source).stem
        extra = []
        if source == 'check-nir-ir-flags.cpp':
            extra = ['-DFMT_HEADER_ONLY', '-I' + str(fmt), '-I' + str(root / 'Eglantine/src'),
                     *['-I' + str(path) for path in boost_includes],
                     str(root / 'headless/nx2-core-check/logging.cpp'),
                     *[str(root / 'Eglantine/src/shader_recompiler/frontend/ir' / (name + '.cpp'))
                       for name in ('microinstruction', 'value', 'type', 'opcodes')]]
        command = [os.environ.get('CXX', 'clang++-18'), '-std=c++20', '-O1',
            '-Wno-macro-redefined', *includes, '-I' + str(root / 'headless'), *extra,
            str(root / 'tools' / source), '-o', str(exe),
            '-Wl,--start-group', *map(str, archives), '-Wl,--end-group',
            '-l:' + (ctypes.util.find_library('zstd') or 'libzstd.so'), '-lz', '-ldl', '-pthread', '-lm']
        subprocess.run(command, cwd=build, check=True)
        subprocess.run([str(exe)], check=True, timeout=60)
        if source == 'check-nir-ir-flags.cpp':
            # A negative control must reproduce the console-discovered union-alias failure.
            bad = Path(tmp) / 'negative-control'
            bad.mkdir()
            header = (root / 'headless/nir_integer_flag_bindings.h').read_text()
            header = header.replace('    // zero/sparse/in-bounds share a union slot.',
                '    (void)inst.GetAssociatedPseudoOperation(Opcode::GetSparseFromOp);\n    // zero/sparse/in-bounds share a union slot.', 1)
            (bad / 'nir_integer_flag_bindings.h').write_text(header)
            broken_exe = Path(tmp) / 'check-broken-union-visitor'
            negative = [command[0], '-I' + str(bad), *command[1:]]
            negative[negative.index('-o') + 1] = str(broken_exe)
            subprocess.run(negative, cwd=build, check=True)
            result = subprocess.run([str(broken_exe)], capture_output=True, text=True, timeout=60)
            if result.returncode == 0 or 'Invalid pseudo-instruction' not in result.stderr:
                raise RuntimeError('IR regression negative control did not detect the old union bug')
            print('NIR IR flag negative control: old union-alias bug rejected PASS')
