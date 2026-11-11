// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdlib>
#include <cstring>
#include "macro_native.h"
#include "macro_bench.h"
#include "common/logging.h"
namespace Eden::MacroNative {
enum class Mode { Off, On, Check };
inline Mode GetMode() {
    static const Mode mode = [] {
        // On by default: only uploaded macros whose SHA-256 matches a signed Mario Kart World
        // layout are replaced, so every other title keeps the JIT. EDEN_NX2_MME_NATIVE=0 turns it
        // off, =check compares on copies and keeps the JIT (docs/MKW-NATIVE-MACROS.txt).
        const char* value = std::getenv("EDEN_NX2_MME_NATIVE");
        if (!value || !*value) return Mode::On;
        return value[0] == '0' ? Mode::Off : std::strcmp(value, "check") == 0 ? Mode::Check : Mode::On;
    }();
    return mode;
}
// Check mode compares effects on copies and leaves the actual call to the JIT.
// Sampling bounds interpreter overhead; every admitted on-mode call is counted.
template <typename Read, typename Write>
bool TryRun(Matcher& matcher, std::span<const u32> code, u64 generation, u32 start,
            std::span<const u32> parameters, std::span<u32> dram, Read read, Write write,
            const char* path) {
    const Mode mode = GetMode();
    if (mode == Mode::Off) return false;
    const Id id = matcher.Find(code, generation, start, kSignatures);
    if (id == None) return false;
    if (mode == Mode::Check) {
        const u64 call = ++matcher.checks[id];
        if (call <= 16 || (call & 4095) == 0) {
            const auto difference = Compare(id, code, start, parameters, dram, read);
            if (!difference.empty()) {
                ++matcher.differences[id];
                LOG_ERROR(HW_GPU, "MME native path={} id={} mismatch={}", path, unsigned(id), difference);
            }
        }
        if (call == 1 || (call & 65535) == 0) {
            LOG_WARNING(HW_GPU, "MME native check path={} id={} calls={} differences={}",
                        path, unsigned(id), call, matcher.differences[id]);
        }
        return false;
    }
    if (!Run(id, parameters, dram, write)) {
        ++matcher.declined[id];
        return false;
    }
    const u64 call = ++matcher.taken[id];
    if (call == 1 || (call & 65535) == 0) {
        LOG_WARNING(HW_GPU, "MME native run path={} id={} calls={} declined={}",
                    path, unsigned(id), call, matcher.declined[id]);
    }
    return true;
}
} // namespace Eden::MacroNative
