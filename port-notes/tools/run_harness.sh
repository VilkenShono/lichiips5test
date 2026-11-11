#!/usr/bin/env bash
# run_harness.sh <port repo> <core tree> <name> [base]
# Instruments the port's CMake rules and runs them against a core tree. With "base", this run is
# the baseline; otherwise misses are compared with out-base (anchors that miss there are optional).
set -uo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
port=$1; core=$2; name=$3; mode=${4:-compare}
work=/home/claude/work
S=/tmp/claude-0/-home-claude/c95c903f-781f-5ce4-b0b1-1945b9374d7f/scratchpad
python3 -I "$here/cmake_instrument.py" "$port" "$work/mirror-$name" >/dev/null
rm -rf "$work/out-$name"; mkdir -p "$work/out-$name"
extra=()
if [[ $mode != base ]]; then
    optional=$(grep -P '^FIND\t' "$work/out-base/harness.log" | cut -f2 | sort -u | paste -sd';')
    extra=(-DHARNESS_FORCE=ON "-DHARNESS_OPTIONAL=$optional")
fi
PATH=$S/stubbin:$PATH cmake -DMIRROR="$work/mirror-$name" -DCORE="$core" -DOUT="$work/out-$name" \
    -DLOG="$work/out-$name/harness.log" -DNATIVE=ON "${extra[@]}" -P "$here/cmake_harness.cmake" > "$work/out-$name/cmake.out" 2>&1
echo "cmake exit=$? (the OpenGL SDK hash at the end is expected to fail here)"
grep -A4 'CMake Error' "$work/out-$name/cmake.out" | grep -v 'libps5_opengl_core33\|file SHA256\|Call Stack\|cmake_harness' | head -20
if [[ $mode == base ]]; then
    cut -f1 "$work/out-$name/harness.log" | sort | uniq -c
else
    # A miss is new when its id (file + needle) did not miss in the baseline.
    cut -f1,2 "$work/out-base/harness.log" | sort -u > "$work/out-$name/base-ids.txt"
    awk -F'\t' 'NR==FNR {seen[$1 FS $2]=1; next} !(($1 FS $2) in seen) && $1 != "DONE" && $1 != "EXEC"' \
        "$work/out-$name/base-ids.txt" "$work/out-$name/harness.log" | grep -v -P '^(FATAL|READ)\t' > "$work/out-$name/new-misses.log"
    echo "new misses: $(wc -l < "$work/out-$name/new-misses.log")"
    cut -f3 "$work/out-$name/new-misses.log" | sed 's/:[0-9]*$//' | sort | uniq -c
    grep -P '^FATAL\t' "$work/out-$name/harness.log" | cut -f4 | cut -c1-150
fi
