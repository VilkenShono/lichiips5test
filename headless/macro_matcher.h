// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
namespace Eden::MacroNative {
enum Id : std::uint8_t { None, ConstBufferSelect, ConstBufferBind, ShaderBind, ShaderUnbind, VertexFormats, ConstBufferSelect128, ConstBufferBind128, ShaderBind128, ShaderUnbind128, VertexFormats128, Count };
struct Signature {
    Id id;
    std::size_t words;
    std::array<unsigned char, 32> sha256;
};
// Owned by the macro engine, with separate front/back states. This avoids shared
// mutable matcher state and invalidates the cache when an engine is recreated.
struct Matcher {
    const std::uint32_t* from{};
    std::size_t size{};
    std::uint64_t version{};
    bool valid{};
    std::array<std::uint8_t, 0x1000> ids{};
    std::array<std::uint64_t, Count> taken{}, checks{}, differences{}, declined{};
    Id Find(std::span<const std::uint32_t> code, std::uint64_t generation, std::uint32_t start,
            std::span<const Signature> signatures);
};
} // namespace Eden::MacroNative
