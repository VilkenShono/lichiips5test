#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Default parallel compile jobs: the core count, capped so each job has about 2 GiB of the
# memory available now (heavy Eden/RADV translation units reach 1.5-2 GiB). 24 jobs on a
# 20 GB machine reached 11 GB and the kernel killed the build and everything beside it.
cores=$(nproc)
available_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
by_memory=$(( available_kib / (2 * 1024 * 1024) ))
jobs=$(( by_memory < cores ? by_memory : cores ))
(( jobs >= 1 )) || jobs=1
echo "$jobs"
