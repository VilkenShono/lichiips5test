#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check native MME safety; optionally compare with interpreter/JIT using private fixtures.

--fixtures accepts a private JSON mapping replacement names to uploaded u32 words.
Only SHA-256 signatures live in the repository. Fixtures stay in a temporary
build directory and are checked against those signatures by the differential test.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixtures', type=Path)
args = parser.parse_args()
cache = Path((root / '.local/headless-cache').read_text().strip())
source = root / 'Eglantine'
with tempfile.TemporaryDirectory() as folder:
    tmp = Path(folder)
    flags = ['-std=c++20', '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
             '-I' + str(root / 'headless'), '-I' + str(source / 'src')]
    objects = [str(root / 'tools/check-macro-native.cpp')]
    if args.fixtures:
        data = json.loads(args.fixtures.read_text())
        names = ['ConstBufferSelect', 'ConstBufferBind', 'ShaderBind', 'ShaderUnbind', 'VertexFormats']
        names += [name + '128' for name in names.copy()]
        if not data or any(name not in names for name in data):
            raise ValueError('Fixtures must contain one or more recognized replacement names')
        text = 'namespace Eden::MacroNative {\n'
        for name in names:
            if name not in data:
                continue
            words = data[name]
            if not words or any(type(word) is not int or not 0 <= word <= 0xffffffff for word in words):
                raise ValueError('Invalid private fixture: ' + name)
            text += 'inline constexpr u32 k' + name + '[] = {' + ','.join(str(word) + 'U' for word in words) + '};\n'
        text += 'inline constexpr std::array<std::span<const u32>, Count> kCode{ std::span<const u32>{}, '
        text += ','.join('k' + name if name in data else 'std::span<const u32>{}' for name in names) + '};\n}\n'
        fixture = tmp / 'private-fixtures.h'
        fixture.write_text(text)
        flags += ['-DEDEN_PRIVATE_MME_FIXTURES="' + str(fixture) + '"', '-DFMT_HEADER_ONLY=1', '-DARCHITECTURE_x86_64=1']
        flags += ['-I' + str(p) for p in (cache / 'source/.cache/cpm/boost').glob('*/libs/*/include')]
        flags += ['-I' + str(p) for p in (cache / 'source/.cache/cpm/xbyak').glob('*') if p.is_dir()]
        flags += ['-I' + str(cache / 'source/.cache/cpm/fmt/12.1.0/include')]
        objects.append(str(root / 'headless/nx2-core-check/logging.cpp'))
    binary = tmp / 'native-check'
    subprocess.run([os.environ.get('CXX', 'c++'), *flags, *objects, '-lcrypto', '-pthread', '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=900)
