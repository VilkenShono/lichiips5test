// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise the production visitor against actual core IR association storage, including its union.
#include <array>
#include <bit>
#include <cstdio>
#include <cstdlib>
#include <optional>
#include "nir_integer_flag_bindings.h"
#include "shader_recompiler/exception.h"

static int RunCases() {
    using namespace Shader::IR;
    constexpr std::array pseudo_ops{Opcode::GetZeroFromOp, Opcode::GetSignFromOp,
                                    Opcode::GetCarryFromOp, Opcode::GetOverflowFromOp};
    unsigned cases{};
    for (const Opcode opcode : {Opcode::IAdd32, Opcode::BitwiseAnd32, Opcode::BitwiseOr32,
                                Opcode::BitwiseXor32, Opcode::BitFieldUExtract, Opcode::BitFieldSExtract}) {
        const unsigned combinations = opcode == Opcode::IAdd32 ? 16 : 4;
        for (unsigned mask = 0; mask < combinations; ++mask) {
            Inst producer{opcode, 0};
            std::array<std::optional<Inst>, 4> pseudos;
            for (unsigned i = 0; i < 4; ++i) {
                if ((mask & (1U << i)) != 0) {
                    pseudos[i].emplace(pseudo_ops[i], 0);
                    pseudos[i]->SetArg(0, Value{&producer});
                }
            }
            // A second visit models NIR rejection followed by re-emission/fallback.
            for (unsigned attempt = 0; attempt < 2; ++attempt) {
                unsigned seen{};
                Eden::Nir::VisitIntegerFlags(producer, [&](Inst& pseudo, Eden::Nir::IntegerFlag flag) {
                    const unsigned index = unsigned(flag);
                    if (index >= 4 || &pseudo != &*pseudos[index] ||
                        pseudo.GetOpcode() != pseudo_ops[index] ||
                        pseudo.Arg(0).InstRecursive() != &producer) std::abort();
                    seen |= 1U << index;
                });
                if (seen != mask || producer.UseCount() != std::popcount(mask)) std::abort();
                for (unsigned i = 0; i < 4; ++i) {
                    if (pseudos[i] && producer.GetAssociatedPseudoOperation(pseudo_ops[i]) != &*pseudos[i]) {
                        std::abort();
                    }
                }
            }
            ++cases;
        }
    }
    std::printf("NIR IR flag bindings: %u real-core association combinations, repeated visits and intact fallback IR PASS\n", cases);
    return 0;
}

int main() {
    try {
        return RunCases();
    } catch (const Shader::Exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
