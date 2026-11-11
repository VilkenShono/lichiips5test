// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "compiler/nir/nir_builder.h"

namespace Eden::Nir {

// UBO words are raw bits, including when the IR names the result F32.
inline nir_def* EmitCbufWord(nir_builder* b, nir_def* descriptor, nir_def* offset,
                             unsigned range_base, unsigned range) {
    return _nir_build_load_ubo(b, 1, 32, descriptor, offset,
                               _nir_load_ubo_indices{0, ACCESS_NON_WRITEABLE, 4, 0,
                                                     range_base, range});
}

inline nir_intrinsic_instr* EmitWriteStorage128(nir_builder* b, nir_def* descriptor,
                                               nir_def* offset, nir_def* value) {
    return _nir_build_store_ssbo(
        b, value, descriptor, nir_iand_imm(b, offset, ~15U),
        _nir_store_ssbo_indices{0, 0xf, static_cast<gl_access_qualifier>(0), 16, 0, 0});
}

inline nir_tex_instr* EmitSampleExplicitLod(nir_builder* b, nir_variable* sampler,
                                           glsl_sampler_dim dim, bool array, bool integer,
                                           nir_def* coords, nir_def* lod,
                                           nir_def* offset = nullptr) {
    nir_deref_instr* const deref{nir_build_deref_var(b, sampler)};
    nir_tex_instr* const tex{nir_tex_instr_create(b->shader, offset ? 5 : 4)};
    tex->op = nir_texop_txl;
    tex->sampler_dim = dim;
    tex->is_array = array;
    tex->coord_components = coords->num_components;
    tex->dest_type = integer ? nir_type_uint32 : nir_type_float32;
    tex->src[0] = nir_tex_src_for_ssa(nir_tex_src_texture_deref, &deref->def);
    tex->src[1] = nir_tex_src_for_ssa(nir_tex_src_sampler_deref, &deref->def);
    tex->src[2] = nir_tex_src_for_ssa(nir_tex_src_coord, coords);
    tex->src[3] = nir_tex_src_for_ssa(nir_tex_src_lod, lod);
    if (offset) tex->src[4] = nir_tex_src_for_ssa(nir_tex_src_offset, offset);
    nir_def_init(&tex->instr, &tex->def, 4, 32);
    nir_builder_instr_insert(b, &tex->instr);
    return tex;
}

} // namespace Eden::Nir
