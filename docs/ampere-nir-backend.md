# Compute shaders to RADV as NIR, without SPIR-V (phase 3 of 3)

The PS5 port links RADV, so a shader can reach the driver in the driver's own intermediate form
(NIR) instead of SPIR-V that RADV would parse back into NIR (`spirv_to_nir`). Phase 3 does this for
compute programs: shorter shader compiles (less stutter), the same GPU code.

## How

- `headless/nir_backend.cpp` translates the emulator IR of a compute program to NIR, mirroring
  what `spirv_to_nir` makes of the SPIR-V backend's output: same descriptor bindings (the unified
  binding order of `EmitContext`), same memory accesses (including the explicit workgroup layout's
  16-bit and 8-byte shared accesses), same float controls and per-instruction NaN/Inf/exactness
  flags, same loop shape and loop safety counters, the guest-warp-sized shuffle semantics.
- The NIR is attached to a `VkShaderModule` made from a SPIR-V header only (`vk_shader_module.nir`,
  as RADV's built-in shaders do); RADV hashes the serialized NIR for its caches. It is freed once
  the pipeline is created (`nir_handoff.h`, core patch 0015).
- A program using anything not translated (an opcode, an indirect buffer, a cube or arrayed
  texture...) keeps the SPIR-V backend. With `EDEN_NX2_COMPILE_TIMES=1` each such program logs
  `NX2_NIR fallback reason=... opcode=...`, which lists what to translate next.
- The backend is built against the pinned RADV's own Mesa headers and its Mesa references are
  renamed like the isolated RADV archive (`headless/nir_backend.cmake`, `tools/isolate-radv.py`).
- On by default; `EDEN_NX2_NIR=0` keeps SPIR-V for every program. Requires subgroup size control
  (the compute pipeline requires guest-sized subgroups).

## Measured

Donkey Kong Bananza, fresh shader cache, same build, `EDEN_NX2_COMPILE_TIMES=1` and
`EDEN_NX2_PIPELINE_STATS=1` (`NX2_COMPILE_TIME` / `NX2_PIPELINE_STATS` in `eden_log.txt`). The two
HMMA (tensor-core) compute shaders, the costliest of the game's compute shaders:

| Shader | SPIR-V emit + RADV | NIR emit + RADV | Change |
| --- | --- | --- | --- |
| 1 (945,633 SPIR-V words) | 8 + 2,098 ms | 82 + 1,391 ms | **-30%** |
| 2 (710,809 SPIR-V words) | 7 + 1,500 ms | 78 + 976 ms | **-30%** |

GPU code (driver statistics), SPIR-V / NIR: instructions 26,106 / 26,136 and 19,418 / 19,426;
VGPRs 104 / 104 and 100 / 100; LDS 12 / 12 KiB and 10 / 10 KiB; latency estimate +1.0% and +2.4%.
Gameplay renders as with SPIR-V (console screenshots), no crash.

The other 19 compute programs of that measured run took SPIR-V: `GetCbufU32x2` (14),
`FPRecip32` (4) and `LoadStorage64` (1). The opt-in expansion below implements these operations;
the 2/21 baseline above describes the earlier reference run, not a coverage gain from this expansion.

## Expanded compute coverage (qualification pending)

Set `EDEN_NX2_NIR_EXTENDED_COMPUTE=1` in `env.txt` to enable the three new translations.
Without it, programs using these operations retain the existing SPIR-V fallback. The global
`EDEN_NX2_NIR=0` switch still disables the entire NIR backend.

- `GetCbufU32x2`: a two-component 32-bit UBO load at the byte offset rounded down to
  eight bytes, matching the SPIR-V descriptor-aliasing path. Dynamic offsets retain that
  path's broken-robustness workaround (a zero vector beyond element index 65535).
- `LoadStorage64`: a two-component 32-bit SSBO load, also rounded down to eight bytes;
  its IR result is a pair of words rather than a scalar 64-bit integer.
- `FPRecip32`: NIR float division of 1.0 by the operand, matching `OpFDiv` and using the
  shader's existing 32-bit float controls.

Vector-buffer loads on profiles without descriptor aliasing and indirect buffer bindings
continue to fall back to SPIR-V. Other unsupported operations retain the same fallback.
These additions remove the three known opcode blockers; they do not establish 21/21
coverage until a fresh-cache console run confirms there are no subsequent blockers.

Local validation (2026-11-05, based on `a946e34`): release build and mandatory package
checks passed, including the focused core suite (179 cases, 2,239,931 assertions).
Candidate `eboot.bin` SHA-256:
`be0a842a0b16ed54d4d490b26750ce16916ba9cb31caba3023323d590f3e181e`.
This hash identifies the uninstrumented release; the console runs below use an input-enabled twin.

Qualification procedure, on the same candidate build and the same save/scene:

1. Compare `EDEN_NX2_NIR_EXTENDED_COMPUTE=0` and `=1`, each with an isolated fresh shader
   cache, `EDEN_NX2_COMPILE_TIMES=1` and `EDEN_NX2_PIPELINE_STATS=1`. Record the build hash,
   per-program fallbacks, emitter/driver times, screenshots and crash evidence.
2. Compare the new programs against `EDEN_NX2_NIR=0`. Require instructions within 0.5%,
   identical VGPR/LDS counts, matching screenshots and no new crash. Count unique program
   hashes, not log lines, for coverage and total compile-time comparisons.
3. Repeat with MKW to identify its next unsupported compute operations. Do not enable
   expanded coverage by default until the console evidence meets these gates.

## Console result for expanded coverage (2026-11-05)

**Verdict: no coverage increase yet; keep the expansion opt-in.** Implementing the first
reported unsupported operation was not sufficient: the translator stops at the first blocker,
so later unsupported operations in the same program were hidden by the original fallback.

Three fresh-cache runs of commit `709f97f`, using the same input-enabled release twin and a
restored copy of the same Bananza "Meet up with others" save, compiled identical sets of
20 compute program hashes in Ingot Isle Cave-In:

| Mode | NIR programs | SPIR-V programs |
| --- | --- | --- |
| Existing NIR, extended coverage off | 2 | 18 |
| NIR with extended coverage on | 2 | 18 |
| NIR disabled | 0 | 20 |

This scene exercised 20 programs, rather than the 21 of the earlier reference run. No
program changed backend between the existing and expanded NIR modes. The expanded run's
next blockers, counted once per unique program hash, were:

| Next blocker | Programs |
| --- | --- |
| Bitwise-operation flags | 8 |
| Integer-add flags | 3 |
| `FindUMsb32` | 3 |
| `WriteStorage128` | 1 |
| `ImageSampleExplicitLod` | 1 |
| `PackUint2x32` | 1 |
| `GetCbufF32` | 1 |

No new application crash was observed; the crash index stayed unchanged and the kernel log
contained no panic, fatal fault or device-lost report during these runs. Expanded-NIR and
SPIR-V screenshots show the same cave geometry, textures and lighting; they are visual
comparisons, not pixel-identical captures (animation and HUD timing differ). Video capture
was intermittent, and the full baseline run has log evidence but no successful gameplay
screenshot. An initial baseline run stopped before full scene coverage is excluded here.

The two existing NIR HMMA programs still match the driver-resource acceptance criteria:

| Metric | Shader 1, SPIR-V / NIR | Shader 2, SPIR-V / NIR |
| --- | --- | --- |
| Instructions | 26,106 / 26,136 (+0.115%) | 19,418 / 19,426 (+0.041%) |
| Allocated VGPRs | 128 / 128 | 128 / 128 |
| LDS bytes | 12,288 / 12,288 | 10,240 / 10,240 |

These checks qualify the existing HMMA path in this scene. They **do not** qualify the new
operations as executable NIR: programs using them still fell back before pipeline creation.
There is no demonstrated compile-time or FPS gain attributable to expanded coverage.
The runs were single observations, not S0's repeated benchmark or a stutter qualification.

Next implementation step: handle the integer add/bitwise flags correctly, then `FindUMsb32`
and the remaining operation gaps above. Repeat this comparison after at least one affected
program reaches NIR pipeline creation; retain the SPIR-V fallback throughout.

Evidence is local under `.local/nir-console/1793864606383304193/`: per-run environment files,
boot/application/frame logs, kernel log, screenshots, program-hash analysis and restoration
receipt. The input twin only adds `MKW_DIAGNOSTIC_INPUT` to the release source temporarily;
it does not enable the per-JIT-run diagnostic timer. Its packaged SELF SHA-256 is
`b6d9aa2f17deb43ca615356f2094205fafcabf7096d4ea243b2b735fe18fa9b4`.
The console's FTP view returns a decoded ELF (verified SHA-256
`759a68db74b1776aa1e2ba5de19881c6b01d31e0973e52eafa16533967b0db14`).

## Integer flag follow-up

The expanded-compute switch now also enables zero/sign flags for bitwise AND/OR/XOR and
signed/unsigned bit-field extracts, plus zero/sign/carry/overflow for 32-bit addition.
Definitions are attached to the associated IR pseudo-instructions without invalidating the
IR: if a later instruction is unsupported, SPIR-V still receives an intact program.
Unresolved or unsupported pseudo-operations continue to fall back.

Carry tests unsigned wraparound; signed overflow tests whether both operands have a different
sign from the sum. Patch 0016 fixes the matching negative-overflow boundary in the existing
SPIR-V and GLSL emitters: `INT32_MIN + (-1)` must set overflow. The negative comparison must
use `INT32_MIN - lhs`, rather than the positive branch's `INT32_MAX - lhs` limit.

`python3 tools/check-nir-integer-flags.py` runs the production flag emitter against the pinned
Mesa's real NIR constant-folding pass. It checks 30,424 cases against independent word and
64-bit arithmetic expectations: boundary/random additions and bitwise operations, and every
valid 32-bit bit-field offset/width for representative words. The checker uses the existing
host RADV CLC build, or `MESA_HOST_BUILD`, without modifying that build. Console coverage and
new-pipeline resource comparisons must be repeated after this follow-up; the table above
records the earlier three-operation implementation, not the flag implementation.

## FindUMsb32 follow-up

`FindUMsb32` now translates to Mesa's `ufind_msb`, behind the same expanded-compute switch.
It returns a zero-based unsigned bit index and `0xffffffff` for zero, matching SPIR-V
`FindUMsb`. The host checker above also exercises the production helper against an independent
bit-by-bit oracle for all 65,536 16-bit words, every 32-bit power of two and its neighbours,
`UINT32_MAX`, and 4,096 deterministic random words (69,729 cases). Integer-flag regressions
continue to run alongside it. Console qualification follows the remaining operation work.

## Remaining compute-operation follow-up

The expanded-compute switch now covers these additional operations:

- `GetCbufF32` shares the raw 32-bit UBO-word load with `GetCbufU32`, preserving bit patterns,
  four-byte alignment and the existing dynamic-offset robustness workaround.
- `PackUint2x32` packs the first word into the low 32 bits and the second into the high 32 bits.
- `WriteStorage128` writes four words with a full component mask at the byte offset rounded
  down to 16 bytes, matching the descriptor-aliasing SPIR-V path. Other binding models fall back.
- `ImageSampleExplicitLod` uses a combined texture/sampler dereference, float coordinates,
  explicit scalar LOD and optional constant integer offset. It supports the existing 1D/2D/3D
  and 1D/2D-array declarations, including integer sampled-image results. Sparse/depth sampling,
  unsupported declarations and dynamic offsets keep the SPIR-V fallback.

The host checker also runs 4,240 word-packing cases through real Mesa folding, checks raw
UBO/SSBO types, binding operands, range metadata, alignment and write masks at ten address
boundaries, and checks twenty texture dimensionality/array/integer/offset combinations using
the production NIR instruction builders. These structural checks do not replace console
sampling validation; fresh-cache coverage, visual and resource comparisons follow this change.

## Follow-up console qualification (2026-11-05)

The first expanded console run exposed an IR-association bug before qualification: the integer
flag visitor queried `GetSparseFromOp` after `GetZeroFromOp`, although zero, sparse and in-bounds
share a union slot in `AssociatedInsts`. A valid zero flag could therefore be interpreted as an
invalid sparse pseudo-operation and reject pipeline creation. The visitor now restricts integer
producers to zero/sign/carry/overflow. A real-core regression covers 36 producer/flag
combinations, visits every binding twice, and verifies that use counts and operands remain intact
for SPIR-V fallback. Its negative control deliberately restores the old sparse query and requires
the core to reject it with `Invalid pseudo-instruction`.

After that fix, three matched, fresh-cache runs of the same Bananza cave scene produced:

| Mode | NIR programs | SPIR-V programs | Pipeline failures |
| --- | --- | --- | --- |
| Existing NIR, expanded coverage off | 2 | 18 | 0 |
| Expanded NIR | 5 | 15 | 0 |
| NIR disabled | 0 | 20 | 0 |

The three newly translated program hashes matched their forced-SPIR-V controls exactly for
instructions, allocated VGPRs and LDS: 47/16/0, 100/32/0 and 103/32/0. The two existing HMMA
programs also remained within the 0.5% instruction gate with identical VGPR/LDS allocation, so
all five NIR programs passed the resource gate. No application restart occurred. At the end of
the run, the harness byte-verified restoration of the original executable, settings and save,
and restored the original shader caches.

The remaining first blockers in this scene are `WriteStorage64` (2 programs), `LoadStorage128`
(8), `FPUnordNotEqual32` (2), `SubgroupBallot` (1), `ShiftRightLogical64` (1) and `FPCos` (1).
The expansion remains opt-in: this single functional qualification establishes additional NIR
coverage and resource parity, but it is not a repeated performance or stutter benchmark.

`tools/check-nir-console.py` automates the leased deployment, load-segment verification,
fresh-cache runs, save/input replay, evidence capture and guarded restoration. Use
`tools/analyze-nir-console.py` to deduplicate program hashes, report fallbacks and compare resource
statistics. `EDEN_SCRIPTED_INPUT=ON` builds the input-enabled qualification twin without enabling
the broader development diagnostics.

## Reproduce

    # env.txt on the console, fresh shader cache
    EDEN_NX2_COMPILE_TIMES=1
    EDEN_NX2_PIPELINE_STATS=1
    EDEN_NX2_NIR=0              # SPIR-V for comparison (default: NIR)
