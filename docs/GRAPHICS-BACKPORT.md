# ProsperoEden graphics backport: measurements

The graphics work backported from ProsperoEden (stacked PRs #56–#60), merged into `main` as
`e27f92f` on top of the Bananza work (#50 feedback-copy coalescing, #53 empty-draw skip), the
memory work (#67–#69) and the fastmem window (#49, #61–#64). On `main` its core patches are
**0025–0033**, after main's own 0018–0024. Its opt-in dense-lazy patch was dropped: main's 0022
(#67) already backs dense GPU-only regions lazily by default.

The measurements below were taken before that merge, on `perf/gfx-on-main` (#72, closed): the
stack merged with the `main` of the time, with the core patches numbered 0020–0029.

## What the stack contains

| PR | Part | Mechanisms (default on unless noted) |
|---|---|---|
| #56 | Pacing and placement | Guest clock slows down to 0.85x when frames are slightly late; vsync compose delay 1.5 ms; guest idle spin 500 µs; secondary threads avoid the GPU thread's SMT sibling; split back thread gets its own core once it exists |
| #57 | GPU memory | Texture GC counts evictions, not visits; short-memory age 600 frames; emptiest-block eviction order; 16 MiB VMA blocks without the double-counting budget extension; idle staging freed while short; pipeline cache rewritten only when it grew |
| #58 | GPU thread | Deferred guest writes while the GPU thread holds a cache lock; 64-page write-ahead; image page map (lock-free reads of memory no image covers); yield to waiting guests; no empty submits; DMA batching; `video_core` built with thin LTO and znver2; perf timers off |
| #59 | Textures | Partial refresh from 1 MiB; BC3 + GPU ASTC by default; ASTC timing policy; 256 MiB transcode cap; layer-at-a-time uploads; lock-free decode handoff; static vertex input |
| #60 | Core patches (0025–0033 on main) | Slot-vector `begin()` fix; split pending releases and QMD shadow; MME DMA read-ahead; register / CB-data blocks; lazy descriptor table; uniform prefetch; macro state writes; ASTC opaque scan table; cache ticks during loads |

## Method

- All candidates are non-development builds with scripted input (`EDEN_SCRIPTED_INPUT=ON`).
  Early numbers in #60 from a development build are superseded by these.
- **#48:** `perf/jit-defaults-on`, the stack's base without its opt-in 64-bit fastmem window.
- **main:** the #53 build (`perf/bananza-draw-path`, #50 + #53). Main also has #46 (page reuse, opt-in, off).
- **main + stack:** `perf/gfx-on-main` (#72).
- Bananza: `tools/bananza-bench-console.py`, warm caches, the pinned Ingot Isle save, inputs
  `55:a,70:a,85:a,100:a`, 240 s. Gate FPS is the median of 5 s windows from t=150 s, when the
  camera faces the neon gate. Walk FPS is the median from 20 to 110 s.
- Mario Kart World: `tools/mkw-bench-console.py`, 1x, warm caches, 240 s.
- Runs interleave candidates (A B C A B C). The console's executable, settings and save are
  restored and verified after every session.
- **Memory:** `EDEN_MEMORY` lines (every ~20 s), giving the smallest "largest free block" of the
  12 GiB pool and the peak guest memory. For MKW: the texture collector's device usage peak
  (`MKW_GC`) and the image footprint.
- **Render accuracy:** screenshots every 15 s (720p capture). Gate shots at the same
  timestamps were compared by eye.

## Donkey Kong Bananza, Ingot Isle neon gate

Two sessions: #48 / main / main + stack, 2 runs each, then main / main + stack, 3 runs each.
All runs are interleaved.

| Build | Completed runs | Gate FPS, median (range) | Gate frame time, median of worst per window | Walk FPS | Smallest pool free block, median (min) | Guest memory peak | Early crashes |
|---|---|---|---|---|---|---|---|
| #48 | 2 | **9.44** (9.42–9.46) | 110 ms | 58.8 | 3332 MiB (2868) | 3711 MiB | 0 of 2 |
| main (#50 + #53) | 4 | **15.50** (15.48–15.52) | 69 ms | 57.3 | 3891 MiB (3400) | 3764 MiB | 1 of 5 (23 s) |
| main + stack | 3 | **16.07** (16.05–16.14) | 70 ms | 58.4 | 4152 MiB (3516) | 3755 MiB | 2 of 5 (28 s, 28 s) |

The stack on its own base (#49, without #50/#53), from an earlier session with 2 runs each:
#48 9.43 → stack 10.08 FPS (+7%), with the gate's worst frame 112 → 103 ms.

- **Performance:** at the gate, main + stack is **+3.7% over main** and +70% over #48. The
  stack's gain is smaller on top of #50's feedback-copy fix, because the gate is then bound by
  per-draw CPU work on the split GPU thread's back, which the stack doesn't change much. Run-to-run
  spread is under 0.1 FPS, so the gain is outside the noise.
- **Frame times:** the gate's slowest frames are the same as main's (69–70 ms). Walking, every
  build is at or near the 60 FPS cap.
- **Memory:** guest memory peaks the same (~3.7 GiB). The pool's largest free block stays
  somewhat larger with the stack (median 4152 vs 3891 MiB), consistent with the 16 MiB VMA blocks
  and the GC changes. That figure moves with fragmentation, so read it as "no regression" rather
  than a firm saving. No run reached short memory.

## Mario Kart World, 1x

| Run | FPS (weighted) | Median 5 s window | Device peak MiB | Images peak MiB | Out of device memory at |
|---|---|---|---|---|---|
| #48 1 | 29.03 | 29.40 | 5904 | 2494 | 183 s |
| stack 1 | – | – | – | – | launch failed (no boot line, no log) |
| #48 2 | 29.02 | 29.14 | 5556 | 2368 | 153 s |
| stack 2 | 33.63 | 34.95 | 6079 | 2537 | 203 s |

- **+16% FPS** in the one completed run (33.6 vs 29.0). The out-of-device-memory crash, the
  known 12 GiB pool exhaustion, still happens in every run, but later.
- This measures the stack on its #49 base, not merged with main; MKW doesn't use #50/#53.

## Render accuracy

- Gate screenshots at the same timestamps (t=150–225 s) show the same scene in all three builds:
  the neon "INGOT ISLE" sign, the gate's lighting, DK, the HUD and the particles. There are no
  missing objects, corrupted textures or colour shifts. Haze on the right comes and goes between
  shots in every build: it's animated dust.
- The loading screens (t=105 s) render correctly in all builds.
- Mario Kart World: the earlier development-build runs captured no images, and the rerun's
  capture failed at the title screen. Not checked by eye.

## Crashes

- **main + stack: 2 of 5 Bananza runs crashed ~13 s after the app started (28 s after launch).**
  The report from the second one: SIGSEGV on the split GPU thread's back (`GPUBack`) in
  `Tegra::Host1x::SyncpointManager::Increment`, called from `RasterizerVulkan::SignalSyncPoint`.
  The first one's report rotated off the console before it was fetched.
- **main: 1 of 5 runs crashed at 23 s;** its report also rotated away. The Bananza thread saw
  intermittent startup crashes on its base build too, with a null image in a RADV barrier at ~13 s.
- None of the stack's core patches touch `SyncpointManager`. Its split-thread patches (0026–0028
  on main) change how the split thread's front and back hand work over, so a timing change
  exposing an existing race is plausible.
- **On `main` after the merge (`e27f92f`, 2026-11-07): 3 of 6 Bananza runs crashed at startup**
  (13–14 s after the app started; same save and inputs, 90 s runs):
  - 2 of 6: the same `SyncpointManager::Increment` crash on GPUBack, from `SignalSyncPoint`, reading
    address `0x10`. That is a list node's `expected_value` read through a null node: the
    syncpoint's action list is corrupt, or the index is out of range. `Increment` holds the lock.
  - 1 of 6: VulkanWorker, a null image in a RADV barrier (`radv_image_queue_family_mask` from
    `radv_barrier` at a render-pass begin): the startup crash seen on the earlier base build too.
  - The pool had ~10 GB free each time, so these are not memory crashes. The other 3 runs ran
    the 90 s at 58.8–59.0 FPS.
  - **Open:** the syncpoint crash needs a fix; the split thread's action registration and the
    syncpoint ids passed to `SignalSyncPoint` are where to look first.
- Mario Kart World: the out-of-device-memory crash (pool exhaustion) happens in every run on
  every build, later with the stack (203 s vs 153–183 s). One stack run failed to start
  (no boot line).
