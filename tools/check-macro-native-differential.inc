// SPDX-License-Identifier: GPL-3.0-or-later
// macro_native.h against the macros it replaces: random and edge-case parameters and data RAM,
// each call run natively, through TuringMacroInterpreter and through TuringMacroJit (what a game
// runs); the method writes and the data RAM must agree. A declined call must leave both alone.
#include <cstdio>
#include <random>
#include <vector>

#include "macro_native.h"
#include "video_core/macro_turing_jit.h"
#include EDEN_PRIVATE_MME_FIXTURES
#include <cassert>
namespace Tegra::GpfifoCapture { bool Configured() noexcept { return false; } void Flush(const char*) noexcept {} }
void AssertFailSoftImpl() { std::abort(); }
[[noreturn]] void AssertFatalImpl() { std::abort(); }
namespace Eden::MacroNative {
inline Id Find(std::span<const u32> code, u64 generation, u32 start) {
    static Matcher matcher; return matcher.Find(code, generation, start, kSignatures);
}
}

using namespace Eden::MacroNative;

int main() {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    BoundaryChecks();
    std::mt19937 random{1};
    const auto pick = [&](std::initializer_list<u32> values) {
        return *(values.begin() + random() % values.size());
    };
    // A parameter or data RAM word: often small or a boundary, sometimes anything.
    const auto word = [&] {
        switch (random() % 4) {
        case 0: return pick({0, 1, 2, 3, 7, 8, 11, 14, 15, 16, 31, 32, 33, 64, 65, 0x75f, 0x760, 0x77f,
                             0x780, 0x7ff, 0x800, 0x7fffffff, 0x80000000, 0xfffffff8, 0xffffffff});
        case 1: return static_cast<u32>(random() % 40);
        case 2: return static_cast<u32>(-static_cast<s32>(random() % 40));
        default: return static_cast<u32>(random());
        }
    };
    u64 checks{}, declined{}, failures{}, generation{};
    for (std::uint8_t id = 1; id < Count; ++id) {
        if (kCode[id].empty()) continue;
        for (const u32 start : {u32{0}, u32{0x75}, u32{0x200}}) {
            std::vector<u32> code(0x3000);
            std::copy(kCode[id].begin(), kCode[id].end(), code.begin() + start * 3);
            ++generation; // each layout its own code generation, as an upload makes
            if (Find(code, generation, start) != id || Find(code, generation, start + 1) == id) {
                std::printf("FAIL %s: not matched at %#x\n", kNames[id], start);
                return 1;
            }
            Tegra::TuringMacroJit jit;
            jit.Prepare(code, generation);
            // Reuse randomized RAM banks; randomizing 3K words per call obscures
            // the interpreter/JIT comparison under sanitizers. Critical table
            // words and one arbitrary word still change on every call.
            std::array<Tegra::TuringMacroInterpreter::DataRam, 16> banks{};
            for (auto& bank : banks)
                for (auto& value : bank) value = random() % 8 == 0 ? word() : 0;
            for (int round = 0; round < 40000; ++round) {
                std::vector<u32> parameters(random() % 3 == 0 ? random() % 8 : 1 + random() % 70);
                for (auto& p : parameters) p = word();
                if (!parameters.empty() && random() % 2) parameters[0] = random() % 70;
                auto dram = banks[round % banks.size()];
                dram[random() % dram.size()] = word();
                const u32 shift = RamShift(static_cast<Id>(id));
                for (const u32 at : {0x4ac + shift, 0x4c3 + shift, 0x4cc + shift}) dram[at] = random() % 2 ? word() : static_cast<u32>(random());
                // The shader bind's early end: the slot already holds this program.
                if ((id == ShaderBind || id == ShaderBind128) && parameters.size() > 1 && random() % 4 == 0 && parameters[0] < (dram.size() - 0x480 - shift) / 4) {
                    dram[0x480 + shift + parameters[0] * 4] = parameters[1];
                }
                const auto read = [](u32) { return 0U; };
                std::string difference = Compare(static_cast<Id>(id), code, start, parameters, dram, read);
                // The same against the JIT.
                auto native_dram = dram, jit_dram = dram;
                std::vector<std::pair<u32, u32>> native_writes, jit_writes;
                const bool ran = Run(static_cast<Id>(id), parameters, native_dram,
                                     [&](u32 m, u32 v) { native_writes.emplace_back(m, v); });
                if (!ran) {
                    ++declined;
                    if (native_dram != dram || !native_writes.empty()) difference = "declined after an effect";
                } else {
                    std::vector<u32> fifo(parameters.begin(), parameters.end());
                    const auto result = jit.Execute(start, fifo, std::span<u32>{jit_dram}, read, [&](u32 m, u32 v) {
                        jit_writes.emplace_back(m, v);
                        return m < 0xe00;
                    });
                    if (difference.empty() && (!result.success || jit_writes != native_writes || jit_dram != native_dram)) {
                        difference = result.success ? "differs from the JIT" : "the JIT fails";
                    }
                }
                ++checks;
                if (!difference.empty() && ++failures <= 10) {
                    std::printf("FAIL %s at %#x: %s; parameters", kNames[id], start, difference.c_str());
                    for (const u32 p : parameters) std::printf(" %x", p);
                    std::printf("\n");
                }
            }
        }
    }
    std::printf("%s: %llu calls (%llu declined), %llu differences\n", failures ? "FAIL" : "PASS",
                static_cast<unsigned long long>(checks), static_cast<unsigned long long>(declined),
                static_cast<unsigned long long>(failures));
    return failures ? 1 : 0;
}
