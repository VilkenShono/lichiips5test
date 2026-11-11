#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Backport ProsperoEden's elevated-app disk cache fix to the pinned console Mesa.

Preserve the desktop identity guard and Mesa's explicit cache-disable setting.
Only the PS5 build may bypass the identity guard, and only with Eglantine's
explicit cache path. Patch the build export, never the Mesa source checkout.
"""
from pathlib import Path
import hashlib
import sys

root = Path(__file__).resolve().parents[1]
fingerprint = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
if sys.argv[1:2] == ['--check']:
    stamp = Path(sys.argv[2])
    raise SystemExit(0 if stamp.is_file() and stamp.read_text().strip() == fingerprint else 1)
if sys.argv[1:2] == ['--digest']:
    print(fingerprint)
    raise SystemExit(0)
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else
          root.parent / 'mihawk-vulkan-review/.deps/work/radv-src')
path = source / 'src/util/disk_cache_os.c'
old = '''   /* If running as a users other than the real user disable cache */
   if (!__normal_user())
      return false;
'''
new = '''   /* EglantinePS5: elevation can change only the effective ids. The app explicitly
    * selects its writable data cache before creating the Vulkan device.
    * Backported from ProsperoEden, scoped to this console app's cache directory. */
   bool eden_console_cache = false;
#if defined(__PROSPERO__)
   const char *eden_cache_dir = getenv("MESA_SHADER_CACHE_DIR");
   eden_console_cache = eden_cache_dir &&
      strcmp(eden_cache_dir, "/data/eglantineps5/cache/radv") == 0;
#endif
   if (!__normal_user() && !eden_console_cache)
      return false;
'''
text = path.read_text()
if new not in text:
    if text.count(old) != 1:
        raise SystemExit('Pinned disk_cache_enabled identity guard changed')
    path.write_text(text.replace(old, new))
    # The upstream builder otherwise returns early when its revision receipt matches.
    receipt = root.parent / 'mihawk-vulkan-review/.deps/native/radv-release/PROVENANCE.txt'
    if source.resolve() == (root.parent / 'mihawk-vulkan-review/.deps/work/radv-src').resolve() and receipt.exists():
        receipt.replace(receipt.with_suffix('.base.txt'))
print('RADV disk cache: elevated PS5 app cache enabled; desktop/disable policies preserved')
