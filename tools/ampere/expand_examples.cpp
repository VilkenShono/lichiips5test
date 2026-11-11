#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <vector>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
// For each Ampere opcode given, print the Maxwell opcode patterns (top 16 bits) it expands into.
int main(int argc, char** argv) {
    std::set<u32> wanted;
    for (int a = 2; a < argc; ++a) wanted.insert(std::strtoul(argv[a], nullptr, 16));
    std::map<u32, std::map<std::string, u64>> shapes;
    for (const auto& entry : std::filesystem::directory_iterator(argv[1])) {
        const auto name = entry.path().filename().string();
        if (entry.path().extension() != ".bin" || name.find(".mapped") != std::string::npos) continue;
        std::ifstream file(entry.path(), std::ios::binary);
        std::vector<Instruction> code; Instruction insn{};
        while (file.read(reinterpret_cast<char*>(&insn), sizeof(insn))) code.push_back(insn);
        auto lowered = LowerToMaxwell(code, false, false);
        if (!lowered) continue;
        const auto& offs = lowered.source_instruction_offsets;
        for (size_t i = 0; i < offs.size(); ++i) {
            const u32 op = code[i].Bits(0, 12);
            if (!wanted.count(op)) continue;
            const u64 end = i + 1 < offs.size() ? offs[i + 1] : lowered.instructions.size();
            std::string shape;
            for (u64 j = offs[i]; j < end; ++j) { char b[8]; std::snprintf(b, 8, "%04x ", unsigned(lowered.instructions[j] >> 48)); shape += b; }
            shapes[op][shape]++;
        }
    }
    for (auto& [op, m] : shapes) {
        std::printf("== 0x%03x\n", op);
        std::vector<std::pair<u64, std::string>> v; for (auto& [s, n] : m) v.emplace_back(n, s);
        std::sort(v.rbegin(), v.rend());
        for (size_t i = 0; i < v.size() && i < 4; ++i) std::printf("  %6llu  %s\n", (unsigned long long)v[i].first, v[i].second.c_str());
    }
}
