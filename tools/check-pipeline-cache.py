#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run real shared-wait concurrency and patched Mesa identity/disable policy checks."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
compiler = os.environ.get('CXX', 'c++')
source = root.parent / 'mihawk-mesa-review'
with tempfile.TemporaryDirectory() as folder:
    tmp = Path(folder)
    wait = tmp / 'wait'
    subprocess.run([compiler, '-std=c++20', '-pthread', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I' + str(root / 'headless'),
                    str(root / 'tools/check-pipeline-wait.cpp'), '-o', str(wait)], check=True)
    subprocess.run([str(wait)], check=True, timeout=30)
    target = tmp / 'src/util/disk_cache_os.c'
    target.parent.mkdir(parents=True)
    target.write_bytes((source / 'src/util/disk_cache_os.c').read_bytes())
    command = ['python3', str(root / 'tools/patch-radv-disk-cache.py'), str(tmp)]
    subprocess.run(command, check=True)
    once = target.read_bytes()
    subprocess.run(command, check=True)
    assert target.read_bytes() == once, 'Patch is not idempotent'
    text = target.read_text()
    start = text.index('bool\ndisk_cache_enabled()')
    body = text[start:text.index('\n}\n', start) + 3]
    stub = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
static bool normal = false;
static bool __normal_user() { return normal; }
static const char* os_get_option(const char* key) { return getenv(key); }
static bool debug_get_bool_option(const char* key, bool fallback) {
    const char* value = getenv(key); return value ? strcmp(value, "true") == 0 : fallback;
}
'''
    tests = r'''
int main() {
    unsetenv("MESA_SHADER_CACHE_DIR"); unsetenv("MESA_SHADER_CACHE_DISABLE");
    unsetenv("MESA_GLSL_CACHE_DISABLE"); unsetenv("MESA_GLSL_DISABLE_IO_OPT");
    normal = true; assert(disk_cache_enabled());
    normal = false; assert(!disk_cache_enabled());
    setenv("MESA_SHADER_CACHE_DIR", "/tmp/other", 1); assert(!disk_cache_enabled());
    setenv("MESA_SHADER_CACHE_DIR", "/data/eglantineps5/cache/radv", 1);
#ifdef __PROSPERO__
    assert(disk_cache_enabled());
#else
    assert(!disk_cache_enabled());
#endif
    normal = true; assert(disk_cache_enabled());
    setenv("MESA_SHADER_CACHE_DISABLE", "true", 1); assert(!disk_cache_enabled());
    normal = false; assert(!disk_cache_enabled());
    unsetenv("MESA_SHADER_CACHE_DISABLE");
    setenv("MESA_GLSL_DISABLE_IO_OPT", "true", 1); assert(!disk_cache_enabled());
}
'''
    (tmp / 'cache.c').write_text(stub + body + tests)
    for flags in [[], ['-D__PROSPERO__']]:
        exe = tmp / 'cache'
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror', *flags,
                        str(tmp / 'cache.c'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print('PASS actual Mesa cache policy: normal/elevated ids, PS5/desktop, wrong path, explicit disable; idempotent patch')
