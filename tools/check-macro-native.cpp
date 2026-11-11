// SPDX-License-Identifier: GPL-3.0-or-later
// Safety checks use synthetic code and data; game bytecode is never bundled.
#include "macro_native.h"
#include <cassert>
#include <limits>
static void BoundaryChecks() {
    using namespace Eden::MacroNative;
    for (unsigned kind = 1; kind < Count; ++kind) {
        std::vector<u32> parameters(140, 0), dram(0x500, 0);
        for (std::size_t length = 0; length < 0x500; ++length) {
            const auto before = dram;
            bool wrote = false;
            assert(!Run(static_cast<Id>(kind), parameters, std::span<u32>(dram.data(), length),
                        [&](u32, u32) { wrote = true; }));
            assert(!wrote && dram == before);
        }
        bool wrote = false;
        const auto before = dram;
        assert(!Run(static_cast<Id>(kind), std::span<const u32>{}, dram,
                    [&](u32, u32) { wrote = true; }));
        assert(!wrote && dram == before);
    }
    std::vector<u32> code{1, 2, 3, 4, 5, 6}; // self-authored arbitrary matching data
    Signature signature{ShaderBind, 3, {}};
    SHA256(reinterpret_cast<const unsigned char*>(code.data()), 3 * sizeof(u32), signature.sha256.data());
    const std::array specs{signature};
    Matcher back, front;
    assert(back.Find(code, 0, 0, specs) == ShaderBind);
    assert(back.Find(code, 0, 1, specs) == None);
    assert(back.Find(code, 0, 0x1000, specs) == None);
    assert(back.Find(code, 0, std::numeric_limits<u32>::max(), specs) == None);
    assert(front.Find(code, 0, 0, specs) == ShaderBind);
    code[0] ^= 1;
    assert(back.Find(code, 1, 0, specs) == None);
    assert(front.Find(code, 1, 0, specs) == None);
    assert(back.Find(std::span<const u32>(code.data(), 2), 1, 0, specs) == None);
    code[0] ^= 1;
    Matcher recreated;
    assert(recreated.Find(code, 0, 0, specs) == ShaderBind);
    // Changing an instruction at the same start cannot match the old signature.
    for (std::size_t word = 0; word < 3; ++word) {
        code[word] ^= 0x80;
        assert(Match(code, 0, specs) == None);
        code[word] ^= 0x80;
    }
    // Full-table minimum is not enough for a variable table read at the tail.
    for (const std::size_t length : {0x500U, 0x501U, 0x502U, 0xbffU}) {
        std::vector<u32> tail_ram(length, 0);
        auto before = tail_ram;
        bool wrote = false;
        const auto emit = [&](u32, u32) { wrote = true; };
        std::array<u32, 5> params{static_cast<u32>(length - 0x4bc), 1, 2, 3, 4};
        assert(!Run(ConstBufferSelect, params, tail_ram, emit));
        assert(!wrote && tail_ram == before);
        params[0] = static_cast<u32>(length - 0x4a0);
        assert(!Run(ConstBufferBind, params, tail_ram, emit));
        assert(!wrote && tail_ram == before);
        params[0] = static_cast<u32>((length - 0x480) / 4);
        if (0x480 + params[0] * 4 + 4 > length) {
            assert(!Run(ShaderBind, params, tail_ram, emit));
            assert(!wrote && tail_ram == before);
        }
    }
    // A rejection must precede all RAM and register effects.
    std::vector<u32> dram(0xc00, 0);
    std::vector<u32> p{65};
    bool wrote = false;
    assert(!Run(VertexFormats, p, dram, [&](u32, u32) { wrote = true; }));
    assert(!wrote);
    std::puts("PASS native MME: short RAM/parameters, no-effect rejection, SHA matching, generation/size/start bounds and engine recreation");
}
#ifdef EDEN_PRIVATE_MME_FIXTURES
#include "check-macro-native-differential.inc"
#else
int main() { BoundaryChecks(); }
#endif
