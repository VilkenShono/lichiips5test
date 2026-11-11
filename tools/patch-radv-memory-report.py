#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-purpose GPU memory report in the pinned console RADV (diagnostic, opt-in).

The PS5 winsys reports one heap usage: every buffer object the driver holds. On Mario Kart
World that reached 7.8 GB while VMA's blocks were 3.5 GB, so ~4.3 GB belonged to the driver's own
objects and the texture collector could never free it. This tallies live bytes and objects by
RADV's buffer priority (application memory <= 28, query pools 29, descriptors / upload buffers /
fences 30, shaders / scratch 31) and prints them to stderr at most every 10 s while
RADV_PS5_MEMORY_REPORT=1 (env.txt). Without the variable it only keeps the counters.
Patches the build export, never the Mesa source checkout.
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
MARK = 'EglantinePS5 memory report'

edits = {
    'src/amd/vulkan/winsys/ps5/radv_ps5_winsys.h': [(
        '''   bool imported;
};
''',
        '''   bool imported;
   /* RADV's priority for the buffer (''' + MARK + '''). */
   uint8_t report_priority;
};

void radv_ps5_memory_report(uint64_t pool, uint64_t available, uint64_t driver);
''')],
    'src/amd/vulkan/winsys/ps5/radv_ps5_bo.c': [(
        '''   p_atomic_add(&radv_ps5_allocated_bytes, bo->memory.bytes);
''',
        '''   p_atomic_add(&radv_ps5_allocated_bytes, bo->memory.bytes);
   bo->report_priority = MIN2(priority, 31u);
   p_atomic_add(&radv_ps5_priority_bytes[bo->report_priority], bo->memory.bytes);
   p_atomic_inc(&radv_ps5_priority_count[bo->report_priority]);
'''), (
        '''   p_atomic_add(&radv_ps5_allocated_bytes, -(int64_t)bo->memory.bytes);
''',
        '''   p_atomic_add(&radv_ps5_allocated_bytes, -(int64_t)bo->memory.bytes);
   p_atomic_add(&radv_ps5_priority_bytes[bo->report_priority], -(int64_t)bo->memory.bytes);
   p_atomic_dec(&radv_ps5_priority_count[bo->report_priority]);
'''), (
        '''uint64_t radv_ps5_allocated_bytes;
''',
        '''uint64_t radv_ps5_allocated_bytes;

/* ''' + MARK + ''': live bytes and buffers by RADV priority. */
static uint64_t radv_ps5_priority_bytes[32];
static int32_t radv_ps5_priority_count[32];

void
radv_ps5_memory_report(uint64_t pool, uint64_t available, uint64_t driver)
{
   static int enabled = -1;
   static int64_t last_ns;
   if (enabled < 0) {
      const char *value = getenv("RADV_PS5_MEMORY_REPORT");
      enabled = value && value[0] == '1';
   }
   if (!enabled)
      return;
   const int64_t now = os_time_get_nano();
   const int64_t previous = p_atomic_read(&last_ns);
   if (previous && now - previous < INT64_C(10000000000))
      return;
   if (p_atomic_cmpxchg(&last_ns, previous, now) != previous)
      return;
   char line[1024];
   int length = snprintf(line, sizeof(line), "RADV_PS5_MEMORY pool_mib=%llu available_mib=%llu driver_mib=%llu",
                         (unsigned long long)(pool >> 20), (unsigned long long)(available >> 20),
                         (unsigned long long)(driver >> 20));
   for (unsigned i = 0; i < 32 && length > 0 && length < (int)sizeof(line) - 48; ++i) {
      const uint64_t bytes = p_atomic_read(&radv_ps5_priority_bytes[i]);
      if (bytes)
         length += snprintf(line + length, sizeof(line) - length, " p%u=%lluMiB/%d", i,
                            (unsigned long long)(bytes >> 20), (int)p_atomic_read(&radv_ps5_priority_count[i]));
   }
   fprintf(stderr, "%s\\n", line);
}
''')],
    'src/amd/vulkan/radv_physical_device.c': [(
        '''   radv_ps5_winsys_heap_usage(&pool, &available, &driver);
''',
        '''   radv_ps5_winsys_heap_usage(&pool, &available, &driver);
   void radv_ps5_memory_report(uint64_t, uint64_t, uint64_t); /* ''' + MARK + ''' */
   radv_ps5_memory_report(pool, available, driver);
''')],
}

includes = {'src/amd/vulkan/winsys/ps5/radv_ps5_bo.c': ['#include <stdio.h>', '#include <stdlib.h>',
                                                         '#include "util/os_time.h"', '#include "util/u_math.h"']}

changed = False
for relative, replacements in edits.items():
    path = source / relative
    text = path.read_text()
    if MARK in text:
        continue
    for old, new in replacements:
        if text.count(old) != 1:
            raise SystemExit(f'{relative}: pinned anchor changed: {old.splitlines()[0]!r}')
        text = text.replace(old, new)
    for include in includes.get(relative, []):
        if include not in text:
            first = text.index('#include')
            text = text[:first] + include + '\n' + text[first:]
    path.write_text(text)
    changed = True
if changed:
    receipt = root.parent / 'mihawk-vulkan-review/.deps/native/radv-release/PROVENANCE.txt'
    if source.resolve() == (root.parent / 'mihawk-vulkan-review/.deps/work/radv-src').resolve() and receipt.exists():
        receipt.replace(receipt.with_suffix('.base.txt'))
print('RADV memory report: per-priority buffer accounting (RADV_PS5_MEMORY_REPORT=1)')
