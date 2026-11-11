// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <utility>
#include "shader_recompiler/frontend/ir/value.h"
#undef UNREACHABLE
#include "nir_integer_ops.h"

namespace Eden::Nir {

template <typename Visitor>
void VisitIntegerFlags(Shader::IR::Inst& inst, Visitor&& visitor) {
    using Shader::IR::Opcode;
    // zero/sparse/in-bounds share a union slot. Only query the zero interpretation for
    // integer producers; querying sparse or in-bounds here rejects a valid zero flag.
    for (const auto& [opcode, flag] : {
             std::pair{Opcode::GetZeroFromOp, IntegerFlag::Zero},
             std::pair{Opcode::GetSignFromOp, IntegerFlag::Sign},
             std::pair{Opcode::GetCarryFromOp, IntegerFlag::Carry},
             std::pair{Opcode::GetOverflowFromOp, IntegerFlag::Overflow}}) {
        if (Shader::IR::Inst* const pseudo{inst.GetAssociatedPseudoOperation(opcode)}) {
            visitor(*pseudo, flag);
        }
    }
}

} // namespace Eden::Nir
