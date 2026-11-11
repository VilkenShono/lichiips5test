// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise the production NIR flag emitter through Mesa's real constant-folding pass.
#include <array>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <random>

#include "nir_integer_ops.h"

static unsigned cases;

static void Check(uint32_t lhs, uint32_t rhs, unsigned operation = 0, unsigned offset = 0,
                  unsigned count = 32) {
    static const nir_shader_compiler_options options{};
    nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE, &options, "integer_flags");
    nir_def* a = nir_imm_int(&b, lhs);
    nir_def* c = nir_imm_int(&b, rhs);
    nir_def* result{};
    uint32_t word{};
    switch (operation) {
    case 0: result = nir_iadd(&b, a, c); word = lhs + rhs; break;
    case 1: result = nir_iand(&b, a, c); word = lhs & rhs; break;
    case 2: result = nir_ior(&b, a, c); word = lhs | rhs; break;
    case 3: result = nir_ixor(&b, a, c); word = lhs ^ rhs; break;
    case 4:
    case 5: {
        nir_def* off = nir_imm_int(&b, offset);
        nir_def* width = nir_imm_int(&b, count);
        result = operation == 4 ? nir_ubitfield_extract(&b, a, off, width)
                                : nir_ibitfield_extract(&b, a, off, width);
        const uint32_t mask = uint32_t((uint64_t(1) << count) - 1);
        word = count == 0 ? 0 : (lhs >> offset) & mask;
        if (operation == 5 && count != 0 && (word & (uint32_t(1) << (count - 1)))) {
            word |= ~mask;
        }
        break;
    }
    default: std::abort();
    }
    constexpr std::array flags{Eden::Nir::IntegerFlag::Zero, Eden::Nir::IntegerFlag::Sign,
                               Eden::Nir::IntegerFlag::Carry, Eden::Nir::IntegerFlag::Overflow};
    std::array<nir_intrinsic_instr*, 4> stores{};
    const unsigned flag_count = operation == 0 ? 4 : 2;
    for (unsigned i = 0; i < flag_count; ++i) {
        nir_def* flag = Eden::Nir::EmitIntegerFlag(&b, flags[i], result, a, c);
        if (flag->bit_size != 1 || flag->num_components != 1) std::abort();
        stores[i] = _nir_build_store_ssbo(
            &b, nir_b2i32(&b, flag), nir_imm_int(&b, 0), nir_imm_int(&b, i * 4),
            _nir_store_ssbo_indices{0, 1, static_cast<gl_access_qualifier>(0), 4, 0, 0});
    }
    while (nir_opt_constant_folding(b.shader)) {}
    const uint64_t wide = uint64_t(lhs) + rhs;
    const int64_t signed_wide = int64_t(std::bit_cast<int32_t>(lhs)) +
                                int64_t(std::bit_cast<int32_t>(rhs));
    const std::array expected{word == 0, (word & 0x80000000U) != 0,
                              wide > UINT32_MAX,
                              signed_wide < INT32_MIN || signed_wide > INT32_MAX};
    for (unsigned i = 0; i < flag_count; ++i) {
        if (!nir_src_is_const(stores[i]->src[0]) ||
            nir_src_as_uint(stores[i]->src[0]) != unsigned(expected[i])) {
            std::fprintf(stderr, "flag %u mismatch for %08x + %08x\n", i, lhs, rhs);
            std::abort();
        }
    }
    ++cases;
    ralloc_free(b.shader);
}

static unsigned find_cases;

static void CheckFind(uint32_t value) {
    static const nir_shader_compiler_options options{};
    nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE, &options, "find_umsb32");
    nir_def* result = Eden::Nir::EmitFindUMsb32(&b, nir_imm_int(&b, value));
    if (result->num_components != 1 || result->bit_size != 32) std::abort();
    nir_intrinsic_instr* store = _nir_build_store_ssbo(
        &b, result, nir_imm_int(&b, 0), nir_imm_int(&b, 0),
        _nir_store_ssbo_indices{0, 1, static_cast<gl_access_qualifier>(0), 4, 0, 0});
    while (nir_opt_constant_folding(b.shader)) {}
    uint32_t expected = UINT32_MAX;
    // Independent reference: walk the word, retaining the last set-bit position.
    for (unsigned bit = 0; bit < 32; ++bit) {
        if ((value & (uint32_t(1) << bit)) != 0) expected = bit;
    }
    if (!nir_src_is_const(store->src[0]) || nir_src_as_uint(store->src[0]) != expected) {
        std::fprintf(stderr, "FindUMsb32 mismatch for %08x\n", value);
        std::abort();
    }
    ++find_cases;
    ralloc_free(b.shader);
}

static unsigned pack_cases;

static void CheckPack(uint32_t low, uint32_t high) {
    static const nir_shader_compiler_options options{};
    nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE, &options, "pack_uint2x32");
    nir_def* result = Eden::Nir::EmitPackUint2x32(
        &b, nir_imm_ivec2(&b, static_cast<int>(low), static_cast<int>(high)));
    if (result->num_components != 1 || result->bit_size != 64) std::abort();
    nir_intrinsic_instr* store = _nir_build_store_ssbo(
        &b, result, nir_imm_int(&b, 0), nir_imm_int(&b, 0),
        _nir_store_ssbo_indices{0, 1, static_cast<gl_access_qualifier>(0), 8, 0, 0});
    while (nir_opt_constant_folding(b.shader)) {}
    const uint64_t expected = uint64_t(low) | (uint64_t(high) << 32);
    if (!nir_src_is_const(store->src[0]) ||
        nir_src_as_const_value(store->src[0])[0].u64 != expected) {
        std::fprintf(stderr, "PackUint2x32 mismatch for %08x %08x\n", low, high);
        std::abort();
    }
    ++pack_cases;
    ralloc_free(b.shader);
}

int main() {
    glsl_type_singleton_init_or_ref();
    constexpr std::array<uint32_t, 12> edges{0, 1, 2, 0x7ffffffe, 0x7fffffff, 0x80000000,
                                             0x80000001, 0xfffffffe, 0xffffffff,
                                             0x55555555, 0xaaaaaaaa, 0x40000000};
    for (const auto a : edges) for (const auto b : edges) {
        for (unsigned op = 0; op < 4; ++op) Check(a, b, op);
    }
    for (const auto a : edges) {
        for (unsigned offset = 0; offset <= 32; ++offset) {
            for (unsigned count = 0; count <= 32 - offset; ++count) {
                Check(a, 0, 4, offset, count);
                Check(a, 0, 5, offset, count);
            }
        }
    }
    std::mt19937 random(0x4e4952);
    for (unsigned i = 0; i < 4096; ++i) {
        for (unsigned op = 0; op < 4; ++op) Check(random(), random(), op);
    }
    for (uint32_t value = 0; value <= UINT16_MAX; ++value) CheckFind(value);
    for (unsigned bit = 0; bit < 32; ++bit) {
        const uint32_t power = uint32_t(1) << bit;
        CheckFind(power);
        CheckFind(power - 1);
        CheckFind(power + 1);
    }
    CheckFind(UINT32_MAX);
    for (unsigned i = 0; i < 4096; ++i) CheckFind(random());
    for (const auto low : edges) for (const auto high : edges) CheckPack(low, high);
    for (unsigned i = 0; i < 4096; ++i) CheckPack(random(), random());
    glsl_type_singleton_decref();
    std::printf("NIR PackUint2x32: %u real Mesa folding cases PASS\n", pack_cases);
    std::printf("NIR FindUMsb32: %u real Mesa folding cases PASS\n", find_cases);
    std::printf("NIR integer flags: %u cases, real Mesa folding, zero/sign/carry/overflow PASS\n", cases);
}
