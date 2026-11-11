// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdlib>
#include <cstring>
#include <x86intrin.h>
#include "macro_native.h"
#include "common/logging.h"
#include "common/cpu_features.h"
namespace Eden::MacroNative {
inline bool BenchEnabled() {
    static const bool enabled = [] {
        const char* value = std::getenv("EDEN_NX2_MME_BENCH");
        return value && std::strcmp(value, "1") == 0;
    }();
    return enabled;
}
inline u64 BenchTick() { _mm_lfence(); return __rdtsc(); }
struct BenchCounter { u64 seen{}, calls{}, ticks{}, emit_ticks{}, writes{}; };
struct BenchState { std::array<BenchCounter, Count> entries; };
// Accessed only when explicitly measuring. Front and back each run on one host
// thread; TLS keeps different contexts/engines from racing without a hot lock.
inline BenchState& BenchCounters(const char* path) {
    static thread_local std::array<BenchState, 2> states{};
    return states[path[0] == 'f' ? 0 : 1];
}
struct Bench {
    BenchCounter* counter{};
    const char* path;
    Id id{None};
    u64 start{}, emit_ticks{}, writes{};
    Bench(Matcher& matcher, std::span<const u32> code, u64 generation, u32 entry, const char* where)
        : path(where) {
        if (!BenchEnabled()) return;
        id = matcher.Find(code, generation, entry, kSignatures);
        if (id == None) return;
        auto& candidate = BenchCounters(where).entries[id];
        if (++candidate.seen <= 1024) return; // leave initial JIT/code upload warmup out
        counter = &candidate;
        start = BenchTick();
    }
    ~Bench() {
        if (!counter) return;
        const u64 elapsed = BenchTick() - start;
        ++counter->calls;
        counter->ticks += elapsed;
        counter->emit_ticks += emit_ticks;
        counter->writes += writes;
        if ((counter->calls & 16383) == 0) {
            LOG_WARNING(HW_GPU, "MME_BENCH path={} id={} calls={} total_ticks={} emit_ticks={} own_ticks={} writes={} tsc_hz={}",
                        path, unsigned(id), counter->calls, counter->ticks, counter->emit_ticks,
                        counter->ticks - counter->emit_ticks, counter->writes, Common::g_cpu_caps.tsc_frequency);
        }
    }
};
struct EmitBench {
    Bench& bench;
    u64 start{};
    explicit EmitBench(Bench& value) : bench(value) { if (bench.counter) start = BenchTick(); }
    ~EmitBench() { if (bench.counter) { bench.emit_ticks += BenchTick() - start; ++bench.writes; } }
};
} // namespace Eden::MacroNative
