// SPDX-License-Identifier: GPL-3.0-or-later
// Inspect the actual production NIR buffer/texture operations and fold their address expressions.
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "nir_compute_ops.h"

static void Require(bool condition) {
    if (!condition) std::abort();
}

static unsigned BufferChecks() {
    static const nir_shader_compiler_options options{};
    unsigned cases{};
    for (const uint32_t address : {0U, 1U, 3U, 4U, 7U, 15U, 16U, 17U, 65535U, 0xffffffffU}) {
        nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE, &options, "buffer_ops");
        nir_def* const descriptor = nir_imm_ivec2(&b, 0, 0);
        nir_def* const word_offset = nir_iand_imm(&b, nir_imm_int(&b, address), ~3U);
        nir_def* const load = Eden::Nir::EmitCbufWord(&b, descriptor, word_offset, address & ~3U, 4);
        const auto* const ubo = nir_instr_as_intrinsic(nir_def_instr(load));
        Require(ubo->intrinsic == nir_intrinsic_load_ubo && load->bit_size == 32 &&
                load->num_components == 1 && ubo->src[0].ssa == descriptor);
        Require(nir_intrinsic_align_mul(ubo) == 4 && nir_intrinsic_align_offset(ubo) == 0 &&
                nir_intrinsic_range_base(ubo) == (address & ~3U) && nir_intrinsic_range(ubo) == 4 &&
                nir_intrinsic_access(ubo) == ACCESS_NON_WRITEABLE);
        // Include a NaN payload and sign-bit pattern: storage must preserve the raw words.
        nir_def* const value = nir_imm_ivec4(&b, 0x12345678, 0x7fc00001, int(0x80000000U), -1);
        nir_intrinsic_instr* const store = Eden::Nir::EmitWriteStorage128(
            &b, descriptor, nir_imm_int(&b, address), value);
        Require(store->intrinsic == nir_intrinsic_store_ssbo &&
                nir_intrinsic_write_mask(store) == 0xf && nir_intrinsic_align_mul(store) == 16 &&
                nir_intrinsic_align_offset(store) == 0 && store->src[1].ssa == descriptor);
        Require(store->src[0].ssa == value && value->num_components == 4 && value->bit_size == 32);
        while (nir_opt_constant_folding(b.shader)) {}
        Require(nir_src_as_uint(ubo->src[1]) == (address & ~3U));
        Require(nir_src_as_uint(store->src[2]) == (address & ~15U));
        ralloc_free(b.shader);
        ++cases;
    }
    return cases;
}

static unsigned TextureChecks() {
    static const nir_shader_compiler_options options{};
    unsigned cases{};
    for (const glsl_sampler_dim dim : {GLSL_SAMPLER_DIM_1D, GLSL_SAMPLER_DIM_2D, GLSL_SAMPLER_DIM_3D}) {
        const unsigned spatial = dim == GLSL_SAMPLER_DIM_1D ? 1 : dim == GLSL_SAMPLER_DIM_2D ? 2 : 3;
        for (const bool array : {false, true}) {
            if (array && dim == GLSL_SAMPLER_DIM_3D) continue;
            for (const bool integer : {false, true}) for (const bool offset : {false, true}) {
                nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_COMPUTE, &options, "sample_lod");
                nir_variable* const sampler = nir_variable_create(
                    b.shader, nir_var_uniform,
                    glsl_sampler_type(dim, false, array, integer ? GLSL_TYPE_UINT : GLSL_TYPE_FLOAT), "tex");
                sampler->data.binding = 7;
                sampler->data.descriptor_set = 0;
                sampler->data.resource_type = nir_resource_type_combined_sampled_image;
                nir_def* const coords = nir_imm_vec4(&b, 0.25, 0.5, 0.75, 1.0);
                nir_def* const lod = nir_imm_float(&b, 2.0);
                nir_def* const delta = nir_imm_ivec3(&b, -1, 0, 1);
                nir_tex_instr* const tex = Eden::Nir::EmitSampleExplicitLod(
                    &b, sampler, dim, array, integer, nir_trim_vector(&b, coords, spatial + unsigned(array)),
                    lod, offset ? nir_trim_vector(&b, delta, spatial) : nullptr);
                Require(tex->op == nir_texop_txl && tex->sampler_dim == dim && tex->is_array == array);
                Require(!tex->is_shadow && !tex->is_sparse && tex->coord_components == spatial + unsigned(array));
                Require(tex->dest_type == (integer ? nir_type_uint32 : nir_type_float32));
                Require(tex->def.bit_size == 32 && tex->def.num_components == 4 &&
                        tex->num_srcs == (offset ? 5U : 4U));
                Require(tex->src[0].src_type == nir_tex_src_texture_deref &&
                        tex->src[1].src_type == nir_tex_src_sampler_deref &&
                        tex->src[0].src.ssa == tex->src[1].src.ssa);
                const auto* const deref = nir_instr_as_deref(nir_def_instr(tex->src[0].src.ssa));
                Require(deref->var == sampler && tex->src[2].src_type == nir_tex_src_coord &&
                        tex->src[3].src_type == nir_tex_src_lod && tex->src[3].src.ssa == lod);
                if (offset) {
                    Require(tex->src[4].src_type == nir_tex_src_offset &&
                            tex->src[4].src.ssa->num_components == spatial);
                    while (nir_opt_constant_folding(b.shader)) {}
                    Require(nir_src_is_const(tex->src[4].src));
                    const nir_const_value* const values = nir_src_as_const_value(tex->src[4].src);
                    for (unsigned component = 0; component < spatial; ++component) {
                        Require(values[component].i32 == int(component) - 1);
                    }
                }
                ralloc_free(b.shader);
                ++cases;
            }
        }
    }
    return cases;
}

int main() {
    glsl_type_singleton_init_or_ref();
    const unsigned buffers = BufferChecks();
    const unsigned textures = TextureChecks();
    glsl_type_singleton_decref();
    std::printf("NIR compute operations: %u buffer and %u texture cases PASS\n", buffers, textures);
}
