// Host tool: runs Shader::Ampere::LowerToMaxwell over dumped native programs and reports, per
// Ampere opcode (bits 0-11), how often it occurs and how many Maxwell instructions it becomes.
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <vector>
#include "shader_recompiler/frontend/ampere/lower_to_maxwell.h"
using namespace Shader::Ampere;
int main(int argc, char** argv) {
    struct Stat { u64 count = 0, out = 0, max = 0; };
    std::map<u32, Stat> stats;
    u64 programs = 0, failed = 0, in_total = 0, out_total = 0;
    std::map<std::string, u64> errors;
    for (int a = 1; a < argc; ++a) {
        for (const auto& entry : std::filesystem::directory_iterator(argv[a])) {
            const auto name = entry.path().filename().string();
            if (entry.path().extension() != ".bin" || name.find(".mapped") != std::string::npos) continue;
            std::ifstream file(entry.path(), std::ios::binary);
            std::vector<Instruction> code;
            Instruction insn{};
            while (file.read(reinterpret_cast<char*>(&insn), sizeof(insn))) code.push_back(insn);
            if (code.empty()) continue;
            ++programs;
            const bool cs = name.find("-cs-") != std::string::npos;
            auto lowered = LowerToMaxwell(code, false, false);
            if (!lowered) { ++failed; errors[std::string(lowered.error)]++; continue; }
            const auto& offs = lowered.source_instruction_offsets;
            for (size_t i = 0; i < offs.size(); ++i) {
                const u64 end = i + 1 < offs.size() ? offs[i + 1] : lowered.instructions.size();
                const u64 n = end - offs[i];
                auto& s = stats[code[i].Bits(0, 12)];
                ++s.count; s.out += n; s.max = std::max(s.max, n);
                ++in_total; out_total += n;
            }
            (void)cs;
        }
    }
    std::printf("programs=%llu failed=%llu ampere=%llu maxwell=%llu ratio=%.2f\n", (unsigned long long)programs,
                (unsigned long long)failed, (unsigned long long)in_total, (unsigned long long)out_total,
                in_total ? double(out_total) / in_total : 0.0);
    for (auto& [e, n] : errors) std::printf("  fail %llu: %s\n", (unsigned long long)n, e.c_str());
    std::vector<std::pair<u64, u32>> by_extra;
    for (auto& [op, s] : stats) by_extra.emplace_back(s.out > s.count ? s.out - s.count : 0, op);
    std::sort(by_extra.rbegin(), by_extra.rend());
    std::printf("op     count    maxwell  avg   max  extra\n");
    for (size_t i = 0; i < by_extra.size() && i < 40; ++i) {
        const auto& s = stats[by_extra[i].second];
        std::printf("0x%03x %7llu %9llu %5.2f %4llu %7llu\n", by_extra[i].second, (unsigned long long)s.count,
                    (unsigned long long)s.out, double(s.out) / s.count, (unsigned long long)s.max,
                    (unsigned long long)by_extra[i].first);
    }
}
