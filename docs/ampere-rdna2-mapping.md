# Ampere shader features on the PS5's RDNA GPU (phase 2 of 3)

What the console's GPU offers for the Switch 2's Ampere shader features, what the emulator can map
onto it, and what Mesa (RADV + ACO, linked into the app) already does. Measured on Donkey Kong
Bananza's two HMMA (tensor-core) compute shaders, the shaders where the mapping matters most.

## Hardware

The PS5 GPU is Mesa's `CHIP_GFX1013` ("GFX10 plus ray tracing instructions";
`mihawk-mesa` `src/amd/vulkan/winsys/ps5/radv_ps5_winsys.c`):

| Feature | GFX1013 | Consequence |
| --- | --- | --- |
| Dot products (`v_dot2_f32_f16`, `v_dot4_*`) | **no** (`has_accelerated_dot_product = false`; "v_dot4_u32_u8 does not compute here") | `VK_VALVE_shader_mixed_float_dot_product` is not exposed; HMMA's products stay FMAs |
| Packed 16-bit math (`v_pk_*`) | yes (`has_packed_math_16bit`) | ACO vectorizes 16-bit ALU on its own |
| Mixed-precision FMA (`v_fma_mix_f32`) | yes | ACO folds f16->f32 conversions into FMAs on its own |
| Wave32 compute, DPP, `ds_bpermute` | yes | quad-local shuffles become DPP; others `ds_bpermute` |
| Cooperative matrices / WMMA | no (RDNA3+) | HMMA is emulated (phase 1, `HMMA_NATIVE`) |

## Measurements

`EDEN_NX2_PIPELINE_STATS=1` (patch 0014) logs the driver's own statistics
(`VK_KHR_pipeline_executable_properties`) of every compute pipeline of 5000 or more instructions
(`NX2_PIPELINE_STATS` in `eden_log.txt`). `EDEN_NX2_IR_STATS=1` (patch 0013) logs the emulator IR.
Bananza, fresh shader cache, same binary, switches in `env.txt`; shader 1 / shader 2:

| Variant | IR instructions | GPU instructions | Copies | Latency | Binary hash |
| --- | --- | --- | --- | --- | --- |
| HMMA as Maxwell sequence (`EDEN_NX2_HMMA_NATIVE=0`) | 303,593 / 227,096 | 27,029 / 20,200 | 1,259 / 906 | 20,892 / 15,818 | 1320380089 / 1452194145 |
| Native HMMA (phase 1) | 93,161 / 69,272 | 26,106 / 19,418 | 683 / 475 | 20,261 / 15,276 | 3680626914 / 2400222582 |
| + A fragments as `QuadBroadcast` (DPP) | 94,505 / 70,280 | 26,106 / 19,418 | 683 / 475 | 20,261 / 15,276 | **same** |
| + f16 operands converted at the FMA (`v_fma_mix` form) | 113,705 / 84,680 | 26,106 / 19,418 | 683 / 475 | 20,261 / 15,276 | **same** |

The driver input differs in every row (different "Driver pipeline hash"), but the last two rows
compile to the **same GPU binary** as native HMMA:

- NIR's `nir_opt_intrinsics` already turns `shuffle(v, (lane & ~3) | k)` into a quad broadcast
  (DPP `quad_perm`), so expressing it in the emulator changes nothing.
- ACO already folds the f16 to f32 conversions into `v_fma_mix_f32`; expressing them as f16
  operands only made the IR 20% larger.
- NIR's CSE already removed most of the duplicated shuffles of the old Maxwell sequence, which is
  why phase 1's 69% IR reduction is 3.5% of GPU instructions (and 46% fewer copies, 3% less latency).

Both mappings were therefore not kept. On this GPU, an emulator-side mapping only pays off where
Mesa cannot see the pattern.

## What is left for the GPU code

- HMMA's B fragments (lane `8(t%4) + 4c + k`) are cross-quad and stay `ds_bpermute`. RDNA's
  `v_permlane16_b32` / `v_permlanex16_b32` could do them without LDS, but SPIR-V cannot express
  them: it needs a NIR-level pattern in the driver, which is where phase 3 (NIR straight to the
  driver) can place it.
- Bananza has few half-precision instructions (337 HADD2, 224 HMNMX2 of 199,492); packed math is
  already ACO's.

## Reproduce

    # env.txt on the console, fresh shader cache (the Bananza driver in .local/mb isolates it)
    EDEN_NX2_IR_STATS=1
    EDEN_NX2_PIPELINE_STATS=1
    EDEN_NX2_HMMA_NATIVE=0      # old Maxwell sequence (default: native)

`VK_PIPELINE_CREATE_CAPTURE_INTERNAL_REPRESENTATIONS_BIT_KHR` (NIR, ACO IR and disassembly) runs
the console out of memory on these shaders; `RADV_DEBUG=shaderstats` stalls the app.
