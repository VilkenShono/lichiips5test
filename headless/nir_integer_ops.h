// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdlib>

#include "compiler/nir/nir_builder.h"

namespace Eden::Nir {

// SPIR-V GLSL.std.450 FindUMsb: a bit index, or all ones for zero input.
inline nir_def* EmitFindUMsb32(nir_builder* b, nir_def* value) {
    return nir_ufind_msb(b, value);
}

inline nir_def* EmitPackUint2x32(nir_builder* b, nir_def* value) {
    return nir_pack_64_2x32(b, value);
}

enum class IntegerFlag { Zero, Sign, Carry, Overflow };

// All inputs/results are 32-bit words; flags are NIR booleans. Only called for requested flags.
inline nir_def* EmitIntegerFlag(nir_builder* b, IntegerFlag flag, nir_def* result,
                                nir_def* lhs = nullptr, nir_def* rhs = nullptr) {
    switch (flag) {
    case IntegerFlag::Zero:
        return nir_ieq_imm(b, result, 0);
    case IntegerFlag::Sign:
        return nir_ilt_imm(b, result, 0);
    case IntegerFlag::Carry:
        return nir_ult(b, result, lhs);
    case IntegerFlag::Overflow:
        // Signed overflow iff both operands' signs differ from the result's sign.
        return nir_ilt_imm(b, nir_iand(b, nir_ixor(b, lhs, result),
                                         nir_ixor(b, rhs, result)), 0);
    }
    std::abort();
}

} // namespace Eden::Nir
