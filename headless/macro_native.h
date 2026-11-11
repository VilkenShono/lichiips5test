// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Native MME equivalents for recognized uploaded programs. Only SHA-256 signatures
// of uploaded code are stored here; game instruction streams are not bundled.
#include <algorithm>
#include <bit>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>
#include <openssl/sha.h>
#include "macro_matcher.h"
#include "video_core/macro_turing.h"
namespace Eden::MacroNative {
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
inline constexpr std::array<const char*, Count> kNames{
    "none", "const buffer select", "const buffer bind", "shader bind", "shader unbind", "vertex formats", "const buffer select +128", "const buffer bind +128",
    "shader bind +128", "shader unbind +128", "vertex formats +128"};
inline constexpr std::array<Signature, Count - 1> kSignatures{{
    { ConstBufferSelect, 12, {0xcc, 0x58, 0xdd, 0x48, 0x09, 0x3b, 0x15, 0x95, 0x92, 0x54, 0xef, 0xb4, 0xc5, 0x10, 0x45, 0xe3, 0x30, 0xab, 0xf2, 0x77, 0xa2, 0x4c, 0xdf, 0x93, 0xb2, 0x40, 0xda, 0x49, 0x76, 0x58, 0xe6, 0x76} },
    { ConstBufferBind, 45, {0x8a, 0x03, 0x7b, 0x29, 0x19, 0x63, 0xd5, 0x11, 0x22, 0x2b, 0xcc, 0xfc, 0xcc, 0xe8, 0x1d, 0x92, 0x25, 0x09, 0x58, 0x3f, 0x3f, 0x74, 0x96, 0x2c, 0xa1, 0x0b, 0xb4, 0x91, 0x60, 0x7f, 0xda, 0x2f} },
    { ShaderBind, 69, {0x56, 0x15, 0x29, 0x53, 0x12, 0xe0, 0x80, 0x26, 0xce, 0xfd, 0x68, 0x53, 0x3f, 0xe4, 0x96, 0xa4, 0x49, 0xe3, 0xd3, 0x0f, 0x1d, 0x7c, 0x04, 0x31, 0xe3, 0x9d, 0x9c, 0x79, 0xc7, 0x4a, 0xd2, 0xc6} },
    { ShaderUnbind, 21, {0x59, 0xa0, 0xdd, 0x34, 0x24, 0x99, 0x10, 0xd8, 0x62, 0x42, 0x07, 0xb1, 0x7d, 0x48, 0x89, 0xf2, 0xc2, 0xcd, 0x8e, 0xa9, 0x4b, 0x67, 0x7a, 0x13, 0xb5, 0x26, 0xc0, 0x68, 0xe7, 0xc5, 0x89, 0xe7} },
    { VertexFormats, 27, {0x3b, 0x12, 0x8d, 0x70, 0x72, 0x8a, 0xaa, 0x07, 0xf0, 0x96, 0xdc, 0x23, 0x51, 0x01, 0x4f, 0xfe, 0xe3, 0xb4, 0xee, 0x90, 0xb1, 0xa1, 0x9f, 0x1f, 0xe9, 0x80, 0x39, 0x21, 0x7f, 0x59, 0xd8, 0xac} },
    { ConstBufferSelect128, 12, {0xd1, 0xb0, 0x3d, 0x1b, 0xac, 0x25, 0x1d, 0x5a, 0x5d, 0xa0, 0x7e, 0xe7, 0x8f, 0xe8, 0x76, 0xf9, 0x2a, 0x2e, 0x27, 0x73, 0x06, 0x27, 0x58, 0x22, 0xe2, 0xed, 0xc0, 0xf6, 0xbd, 0xfd, 0x27, 0x80} },
    { ConstBufferBind128, 45, {0xf3, 0xc5, 0x5a, 0xf9, 0x4c, 0xce, 0x9d, 0xa8, 0xe6, 0xdd, 0x02, 0xab, 0x4d, 0x47, 0x2b, 0xb7, 0xa1, 0x31, 0x2b, 0x67, 0x0b, 0x04, 0x5d, 0x4c, 0x17, 0x82, 0x09, 0x2a, 0x1a, 0x36, 0xf6, 0x55} },
    { ShaderBind128, 69, {0x10, 0xef, 0x0a, 0x5b, 0x57, 0xdb, 0x10, 0x10, 0x78, 0x88, 0xda, 0x61, 0xa3, 0x39, 0x49, 0xda, 0xb7, 0x48, 0x98, 0xff, 0xc7, 0x49, 0xee, 0x31, 0x4c, 0xf3, 0x3d, 0xd0, 0x56, 0xa1, 0x17, 0xb7} },
    { ShaderUnbind128, 21, {0x2a, 0xa4, 0xd9, 0xac, 0x10, 0xec, 0x4e, 0x87, 0x6c, 0x4e, 0x37, 0x3b, 0x8e, 0xd7, 0xed, 0x14, 0x58, 0xfc, 0x2b, 0x85, 0x01, 0xfd, 0x1b, 0xdf, 0xe6, 0x13, 0xee, 0xd9, 0xda, 0x64, 0x7d, 0x37} },
    { VertexFormats128, 27, {0x87, 0xe1, 0xc2, 0x09, 0x47, 0x53, 0x7f, 0xac, 0x38, 0xc1, 0xd5, 0x42, 0x9b, 0x47, 0xab, 0xad, 0xf4, 0x2f, 0x7f, 0xc5, 0x19, 0x40, 0xc5, 0x90, 0x72, 0x98, 0x7b, 0x6c, 0x11, 0x75, 0x43, 0x24} },
}};
inline Id Match(std::span<const u32> code, u32 start, std::span<const Signature> signatures) {
    static_assert(std::endian::native == std::endian::little);
    const std::size_t offset = std::size_t{start} * 3;
    if (offset >= code.size()) return None;
    for (const auto& signature : signatures) {
        if (signature.words > code.size() - offset) continue;
        std::array<unsigned char, SHA256_DIGEST_LENGTH> hash{};
        SHA256(reinterpret_cast<const unsigned char*>(code.data() + offset),
               signature.words * sizeof(u32), hash.data());
        if (hash == signature.sha256) return signature.id;
    }
    return None;
}
inline Id Matcher::Find(std::span<const u32> code, u64 generation, u32 start,
                        std::span<const Signature> signatures) {
    if (start >= ids.size()) return None;
    if (!valid || from != code.data() || size != code.size() || version != generation) {
        valid = true; from = code.data(); size = code.size(); version = generation;
        ids.fill(0xff);
    }
    auto& id = ids[start];
    if (id == 0xff) id = Match(code, start, signatures);
    return static_cast<Id>(id);
}
// 0x75 (1 parameter): the constant buffer selected for data uploads (size, address) from the
// data RAM table at 0x4bc.
template <typename Write>
bool RunConstBufferSelect(std::span<const u32> p, std::span<u32> dram, Write& write, u32 shift = 0) {
    if (p.size() < 1) return false;
    const u32 index = 0x4bc + shift + p[0];
    if (index >= dram.size()) return false;
    const u32 entry = dram[index];
    write(0x8e0, dram[0x4c3 + shift]);
    write(0x8e1, entry >> 24);
    write(0x8e2, (entry & 0xffffff) << 8);
    return true;
}

// 0x21 (stage or slot, index, address low, size and address high): binds a constant buffer to a
// stage; from slot 8 on, the stage comes from the data RAM table at 0x4a0 and the buffer is kept
// in the table at 0x400.
template <typename Write>
bool RunConstBufferBind(std::span<const u32> p, std::span<u32> dram, Write& write, u32 shift = 0) {
    if (p.size() < 4) return false;
    u32 stage = p[0];
    if (!(static_cast<s32>(p[0]) < 8)) {
        const u32 table = 0x4a0 + shift + p[0];
        if (table >= dram.size()) return false;
        const u32 slot = (0x400 | (p[0] & 3) << 5 | (p[1] & 15) << 1) + shift;
        stage = dram[table];
        dram[slot] = p[2];
        dram[slot + 1] = p[3];
    }
    if (!(static_cast<s32>(stage) < 15)) return true;
    write(0x8e0, (p[3] >> 12) & 0xfffff);
    write(0x8e1, p[3] & 0xff);
    write(0x8e2, p[2]);
    write(0x904 + (stage & 7) * 8, 1 | ((p[1] + 3) & 0xfffffff) << 4);
    return true;
}

// 0x8 (slot, program offset, constant buffer address, address, configuration): a shader stage's
// program and its constant buffer 1; nothing when the data RAM table at 0x480 already has it,
// writes only when the slot is enabled (data RAM 0x4ac).
template <typename Write>
bool RunShaderBind(std::span<const u32> p, std::span<u32> dram, Write& write, u32 shift = 0) {
    if (p.size() < 5) return false;
    const u32 base = 0x480 + shift + p[0] * 4;
    if (base > dram.size() - 4) return false;
    if (p[1] == dram[base]) return true;
    const u32 enabled = dram[0x4ac + shift];
    dram[base] = p[1];
    dram[base + 1] = p[2];
    dram[base + 2] = p[3];
    dram[base + 3] = p[4];
    if ((enabled & (1U << (p[0] & 31))) == 0) return true;
    const u32 program = ((p[4] >> 24) & 7) * 16, bind = ((p[4] >> 28) & 7) * 8;
    write(0x805 + program, p[2] >> 24);
    write(0x806 + program, (p[2] & 0xffffff) << 8);
    write(0x807 + program, (p[4] >> 9) & 0x7f);
    write(0x8e0, 0x10000);
    write(0x8e1, p[3] >> 24);
    write(0x8e2, (p[3] & 0xffffff) << 8);
    write(0x904 + bind, 0x11);
    write(0x803 + program, p[4] & 0x1ff);
    write(0x800 + program, 1 | program);
    return true;
}

// 0x188 (slot and program): forgets the slot's program in the table at 0x480 and turns the
// program off when the slot is enabled.
template <typename Write>
bool RunShaderUnbind(std::span<const u32> p, std::span<u32> dram, Write& write, u32 shift = 0) {
    if (p.size() < 1) return false;
    const u32 slot = p[0] & 15, program = ((p[0] >> 4) & 7) * 16;
    const u32 enabled = dram[0x4ac + shift];
    dram[0x480 + shift + slot * 4] = 0;
    if (enabled & (1U << slot)) write(0x800 + program, program);
    return true;
}

// 0x319 (count, then count pairs): vertex attribute formats from 0x458; the ones the previous
// call set beyond count (data RAM 0x4cc) get 0x3a400040.
template <typename Write>
bool RunVertexFormats(std::span<const u32> p, std::span<u32> dram, Write& write, u32 shift = 0) {
    // shortcut: up to 64 pairs either way (the hardware has 32), the JIT runs anything larger.
    if (p.size() < 1 || p[0] > 64 || p.size() < 1 + std::size_t{p[0]} * 2) return false;
    const u32 count = p[0], rest = dram[0x4cc + shift] - count;
    if (static_cast<s32>(rest) > 64) return false;
    u32 method = 0x458;
    for (u32 i = 0; i < count * 2; ++i) write(method++, p[1 + i]);
    dram[0x4cc + shift] = count;
    if (static_cast<s32>(rest) <= 0) return true;
    for (u32 i = 0; i < rest * 2; ++i) write(method++, 0x3a400040);
    return true;
}

inline constexpr u32 RamShift(Id id) { return id >= ConstBufferSelect128 ? 0x80U : 0U; }

// Runs replacement `id`; false: the macro's own code must run the call (nothing was done).
template <typename Write>
bool Run(Id id, std::span<const u32> parameters, std::span<u32> dram, Write&& write) {
    if (dram.size() < 0x500 + RamShift(id)) return false;
    switch (id) {
    case ConstBufferSelect: return RunConstBufferSelect(parameters, dram, write);
    case ConstBufferBind: return RunConstBufferBind(parameters, dram, write);
    case ShaderBind: return RunShaderBind(parameters, dram, write);
    case ShaderUnbind: return RunShaderUnbind(parameters, dram, write);
    case VertexFormats: return RunVertexFormats(parameters, dram, write);
    case ConstBufferSelect128: return RunConstBufferSelect(parameters, dram, write, 0x80);
    case ConstBufferBind128: return RunConstBufferBind(parameters, dram, write, 0x80);
    case ShaderBind128: return RunShaderBind(parameters, dram, write, 0x80);
    case ShaderUnbind128: return RunShaderUnbind(parameters, dram, write, 0x80);
    case VertexFormats128: return RunVertexFormats(parameters, dram, write, 0x80);
    default: return false;
    }
}

// Runs replacement `id` and the interpreter on copies of the data RAM: "" when the replacement
// declines the call or both make the same method writes and leave the same data RAM; otherwise
// what differs. `read` is MME_READ of a register (none of the replacements reads one).
template <typename Read>
std::string Compare(Id id, std::span<const u32> code, u32 start, std::span<const u32> parameters,
                    std::span<const u32> dram, Read read) {
    using Interpreter = Tegra::TuringMacroInterpreter;
    Interpreter::DataRam native_dram{}, reference_dram{};
    std::copy_n(dram.begin(), std::min(dram.size(), native_dram.size()), native_dram.begin());
    reference_dram = native_dram;
    std::vector<std::pair<u32, u32>> native_writes, reference_writes;
    if (!Run(id, parameters, native_dram, [&](u32 method, u32 value) { native_writes.emplace_back(method, value); })) {
        return {};
    }
    Interpreter interpreter;
    interpreter.active_dram = &reference_dram;
    std::vector<u32> fifo(parameters.begin(), parameters.end());
    const auto result = interpreter.Execute(code, start, fifo, read, [&](u32 method, u32 value) {
        reference_writes.emplace_back(method, value);
        return method < 0xe00;
    });
    std::string difference;
    if (!result.success) {
        difference = "the macro fails (" + std::string{result.error} + ")";
    } else if (native_writes != reference_writes) {
        difference = "writes differ:";
        for (std::size_t i = 0; i < std::max(native_writes.size(), reference_writes.size()); ++i) {
            const auto show = [](const auto& writes, std::size_t i) {
                if (i >= writes.size()) return std::string{"-"};
                char text[32];
                std::snprintf(text, sizeof(text), "%x=%x", writes[i].first, writes[i].second);
                return std::string{text};
            };
            difference += " " + show(native_writes, i) + "/" + show(reference_writes, i);
        }
    } else if (native_dram != reference_dram) {
        const auto at = std::mismatch(native_dram.begin(), native_dram.end(), reference_dram.begin()).first -
                        native_dram.begin();
        char text[64];
        std::snprintf(text, sizeof(text), "data RAM differs at %#zx: %x/%x", static_cast<std::size_t>(at),
                      native_dram[at], reference_dram[at]);
        difference = text;
    }
    return difference;
}

} // namespace Eden::MacroNative
