# Mario Kart World title screen: frame rate on the console

Status: 2026-11-02. The title screen went from about 11 FPS to about 24 FPS on the same core
(Zortos `3140648a`) and driver (RADV, pinned Mesa). 40 FPS is not reached; what is left is
measured below. Every number is one console run of a 45-60 s window at the title (the attract
scene varies between runs by about 2 FPS), with the `EDEN_VULKAN_FRAME` counter of `heap.log`.

## What was wrong

The console has no fastmem arena for 64-bit games: every guest read of a page the GPU caches
track leaves the JIT, and when the per-core area cache misses, it was answered by the GPU
thread (an "ordered read": the guest core sleeps, the GPU thread wakes, answers, the core
wakes). With the port's high GPU accuracy every fence also waited for the console's GPU and the
core's split GPU thread stayed off. Profiles of the baseline (ps5-perf, precise and off-CPU):

- the process used 2.6 of 8 CPUs; the GPU thread idled 40-47% waiting for commands while the
  guest's main core spent 54% of its wall time in `HostCommandCompletion::Wait`;
- the Vulkan driver got 1,000-3,700 submissions a second (one per fence), each a cache flush,
  an AGC submit and a 0.3 ms suspend point;
- 12% of the GPU thread's wall time was `fopen`/`fclose`/`_write` of per-process dump files
  (patch 0005 gates them behind `EDEN_NX2_READBACK_DIAGNOSTICS`);
- the texture collector sat in aggressive mode (the port measures GPU memory as the budget
  less the shared pool's largest free block, and the guest holds 4.3-4.8 GB of the 11.1 GB
  pool at the title), re-uploading ~3,000-4,500 textures per 600 frames.

## What changed

| Change | Where | Title FPS |
|---|---|---|
| Baseline: high accuracy, reactive flushing, no split thread | - | 10.9 |
| Low accuracy (fast GPU fences), reactive flushing off | performance settings | 12.0 |
| + the core's split GPU thread (needs the two above) | fixed a crash, below | 13.1 |
| + guest reads with nothing to flush answered on the guest core (`EDEN_NX2_UNSAFE_PREEMPTIVE_READS=1`, as fastmem builds do) | main.cpp default | 19.9 |
| + the split's front checks the written-page bits before draining the back for a command list | patch 0006 | 21.8-24.2 |
| + 300 us spin waits before the three sleeps of a read round trip | patch 0006, main.cpp default | within noise |
| Final defaults (candidate 11): 5 s windows 21-29 FPS, 24.4 average over 48 s, then out of device memory at 139 s | - | 24.4 |
| + `EDEN_NX2_TC_COSTLY_MIN_AGE=30` | env.txt | 24.7 |

The split GPU thread crashed on the console: the port presented its loading screen from the
front thread while the back thread composited the guest's frames, both recording into one
scheduler (a descriptor set allocation failed, then `Layer::ConfigureDraw` dereferenced the
empty set). The present now goes through the split's ring (`headless/graphics.cpp`).

Switch 2 titles (program ids `0400...`) default to fast GPU fences and no reactive flushing
in the port's performance settings; the game's own values in the Library still win.

## What is left (profile of the 24 FPS configuration)

- The split's back thread is the limit: ~0.7-0.9 of a core at 22 FPS, of which engine method
  calls ~20% (2 million a second), draw setup ~35% (26,000-30,000 draws a second), texture
  uploads ~15% (re-uploads of collected ASTC images), fences ~3%, ring dispatch ~19%.
- The front still waits for the back for command lists on GPU-written pages. Checking a
  semaphore acquire against the guest's own word before draining is on (23.1 FPS, within the
  run-to-run noise of the full drain; `EDEN_NX2_ACQUIRE_DRAIN_FIRST=1` restores the drain).
  Waiting only up to the last compute, copy or upload method crashed the game while loading on
  two candidates (a list read before its writer ran, then a clear with a garbage render
  target), so it is off unless `EDEN_NX2_LIST_DRAIN_TO_WRITER=1`: something the front does not
  count as a writer fills those lists.
- Memory: the guest's committed memory grows through the title screen (4.3 -> 4.8 GB in two
  minutes) while the texture cache holds ~2-4 GB of host copies and the heap ~1.9 GB in an
  11.1 GB pool; low-accuracy runs end with `VK_ERROR_OUT_OF_DEVICE_MEMORY` after 1.5-3
  minutes. The 20 s memory report now also prints the kernel's count of the guest's mapped
  memory: 9.2 GB at the title. The core gives every Switch 2 title its 12 GiB layout
  ("titles size their heap from the total memory") and the game maps nearly all of it; the
  sparse backing commits only the pages it writes, which is where the growth comes from.
  `EDEN_NX2_MEMORY_LAYOUT_GB=6|8|10` runs the title with a smaller layout (its graphics server
  region stays): with 8 and with 6 GiB the game faulted at a null pointer during its boot (it
  never mapped memory), so its heap sizing needs the 12 GiB layout as the core says. Fitting
  the title screen in the pool needs smaller host copies (fewer, smaller or shared textures),
  not a smaller guest. 16 MiB VMA blocks (`EDEN_PS5_VMA_BLOCK_MIB=16`, 19.5 FPS, out of
  memory at 168 s) and the transient image pools (`EDEN_PS5_TRANSIENT_POOLS=1`, 23.2 FPS, out
  of memory at 155 s) changed neither the frame rate nor the time to exhaustion.
- Compiling the emulator for the console's Zen 2 (`EDEN_CPU_PRESET=zen2`, `-march=znver2`;
  the default is generic x86-64) measured 19.8 and 22.6 FPS: no gain over the generic build.
- A function-level profile of the back thread at 22 FPS: 39% the draw path (pipeline
  configure 26%, image views 10%, stage buffers 5%), 15% compute dispatch and its QMD
  signals, 16% texture churn (deleting 7%, creating 5%, re-uploading 4%), 11% mutex locks
  (the Vulkan worker's poll retaking the queue mutex, invalidations under inline uploads), 15%
  idle. The worker poll now reads an atomic count and the published semaphore store uses a
  spin lock (candidate 15: 21.8 and 20.8 FPS, within the 20-25 FPS run-to-run band). What is
  left in the draw path and the churn is core work beyond a settings or synchronization fix.
- Not recording CPU-read buffer ranges (`EDEN_NX2_CPU_READ_RANGES=0`, which stops the
  per-fence copy-backs those ranges cause: ~3,700 real fences a second) measured 20.0 FPS
  against 24.6 for the control in the same run, and ran out of memory sooner: the fences
  are not the limit either. `EDEN_NX2_TC_COSTLY_MIN_AGE` keeps
  recently used decoded ASTC images out of aggressive collection (fewer re-uploads, less
  headroom).
- The core's `EDEN_NX2_GPU_PROFILE` costs ~25% of the GPU thread's CPU on the console (clock
  reads and emulated TLS); never read final frame rates with it on.

## Where the frame time goes (branch perf/mkw-core-draw-path, 2026-11-03)

The GPU side keeps up with the game: at the title the vi2 present never waits for the GPU
fence (2 us average over 600 presents), and none of the renderer-side changes moved the
title's 23-26 FPS band, measured one after another on the same binary:

| Change (all opt-in knobs on this branch unless noted) | Title FPS |
|---|---|
| Control | 23-26 |
| GPU-written command lists skip the front-to-back drain unless marked in the last 4M ring words, dirty or with a writer queued (`EDEN_NX2_LIST_DRAIN=recent`; 96% of 13,000 drains a second skipped, front 1,700 words ahead instead of 57) | 24.6 |
| Semaphore acquires drain only to the semaphore's queued release (`EDEN_NX2_ACQUIRE_DRAIN_TO_RELEASE=1`) | 23.2 |
| Two frames in flight at the present (`EDEN_NX2_FRAMES_AHEAD=2`), renderer present thread (`EDEN_PS5_PRESENT_THREAD=1`) | 25.7, 21.3 |
| Half render resolution, 120 Hz guest vsync (`EDEN_NX2_VSYNC_HZ=120`) | 23.1, 24.8 |
| Unsafe CPU accuracy, plus unsafe DMA and skipped invalidation | 23.4, 24.2 |
| Guest idle spin 1 ms instead of 100 us (`idle_spin_us`), kernel spin lock 2048 pauses (`EDEN_PS5_KSPIN`) | 19.0, 19.7 |
| Guest cores 4-5 and the GPU threads on their own CPUs (`EDEN_PS5_PLACE`) | 25.6, 23.6 |
| No per-delete walk of the TIC index map, one-word ASTC opacity scan, bounded transcode reclaim (patch 0007 defaults) | within noise; the second shortens the time to device memory exhaustion |

What the guest does instead (development profile build, `EDEN_DEV_PROFILE=ON`, and the
`EDEN_GUEST_RUN` / `EDEN_GUEST_WAKE` lines of the normal build's 5 s report):

- The game's main thread waits 82% of the time, 3.2 s of every 5 in address arbitration on
  its own job system: ~77 waits a frame, 350 us each on average. Its six `BaseProcExecutor`
  threads carry the work (0.26-0.44 of a core each, ~70 us of guest code per run, 5-6k runs a
  second each) and are themselves idle 56-74%; the main thread runs 0.14 of a core, the
  loaders and `gear::PrepareThread` little.
- Host wake-up latency is not the cost: a sleeping guest core resumes 7-9 us after the
  interrupt that wakes it (worst 70-575 us), 25k idles a second on core 0, a third of them sleeps.
- The guest cores' time: 53% JIT-compiled game code, 33% idle spin, 10% emulated kernel
  (3.4% futex syscalls, 2.7% the scheduler spin lock's clock-polling wait), 3.5% memory
  callbacks. IPC averages a millisecond (storage reads on the loaders); the main thread's own
  IPC is 13 ms per 5 s.

So the title's frame is the serial chain main thread -> executor jobs -> main thread, with
the busiest executor's job code (18 ms a frame of JIT'd code at 24 FPS) and the main thread's
7 ms on its critical path. 40 FPS needs that guest code to run ~1.7x faster: a 64-bit fastmem
arena on the console (every memory access walks the page table today) and dynarmic code
quality, not renderer or scheduling work.

Reproduce: `tools/mkw-title/run.py` as above; `fold.py` folds a ps5-perf recording for
`stacks.py`; the runner relaunches when a crash notice sends the app to the launcher.

## Reproduce

Build in the usual container (`docs/BUILDING.md`), with `EDEN_PS5_VULKAN=ON` and
`EDEN_VULKAN_DRIVER=RADV`, and package into `build/<name>/PPSA98515`. Then, under the console
lease:

```
python3 tools/console-lease.py --host 192.168.0.190 run --wait -- \
  env MKW_CANDIDATE=<name> python3 tools/mkw-title/run.py .local/exp \
  "prod:fast_gpu=true,reactive_flushing=false,measure=60;control:fast_gpu=true,reactive_flushing=false,env=EDEN_NX2_LIST_DRAIN_FULL=1|EDEN_NX2_ACQUIRE_DRAIN_FIRST=1"
python3 tools/mkw-title/analyze.py .local/exp/<run>
python3 tools/mkw-title/stacks.py .local/exp/<run>/prod precise GPU,GPUBack,CPUCore_0 3
```

`run.py` deploys the candidate's `eboot.bin`, writes the game's performance settings and an
`env.txt` (the port's development switch file: `NAME=VALUE` lines read before the core starts,
`EDEN_LOG_FILTER` names a log filter), launches the game through `launch.elf` (built from
`launch.c` with the payload SDK), waits for the title (800 presented frames), measures,
records ps5-perf precise and off-CPU profiles with the build's matched ELF, keeps live log
tails (the crash handler's restart truncates them), and restores the settings file and the
original `eboot.bin`.

AI assistance: the investigation, the changes and this document were made with Claude Code.
