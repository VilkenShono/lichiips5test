# Mario Kart World console benchmark

`tools/mkw-bench-console.py` is the standard way to compare builds on the console. It replaces
one-off runners whose numbers could not be compared with each other.

## What it does

- Takes the shared console lease, uploads each candidate, verifies its PT_LOAD bytes against the
  matching ELF, and restores the original executable, settings, save and caches at the end.
- Interleaves candidates and variants (A B A B …) so console drift and shader-cache progress
  affect both sides alike.
- `--cache warm` (default) primes the caches with one unmeasured run, then keeps them for every
  measured run. `--cache cold` clears them before each run.
- Measures only after the intro: windows of the game's presented-frame counter
  (`EDEN_VULKAN_FRAME`) once 800 frames have been shown.
- A crash ends that run but not the sequence. The runner records the reason (for example
  `VK_ERROR_OUT_OF_DEVICE_MEMORY`) and the seconds after launch, and keeps the crash report and
  log copies. Logs are copied every 10 s, because the restart after a crash truncates them.
- Records device-memory peaks from the texture collector (`MKW_GC usage`) and the image
  footprint (`MKW_IMAGE_FOOTPRINT`).
- Takes a title screenshot 45 s after the game loads, plus one at the end or after a crash.
- Writes `results.json` and `report.md` (per-run and per-candidate tables).

```
python3 tools/mkw-bench-console.py --host 192.168.0.190 \
  --launcher LAUNCH.elf --out .local/bench/NEW_DIR \
  --candidate base=BASE.bin,BASE.elf --candidate new=NEW.bin,NEW.elf \
  --variant 'default' --variant 'native|EDEN_NX2_MME_NATIVE=1|@fast_gpu=true' \
  --runs 2 --seconds 240 --resolution 0.5x
```

Candidates must be input-enabled builds (`EDEN_SCRIPTED_INPUT=ON`) so a run can return to the
launcher normally. In a variant, `NAME=VALUE` items become `env.txt` lines and `@key=value` sets
the title's performance setting. `EDEN_LOG_FILTER=*:Warning Render.Vulkan:Info` is always set,
so the console's *detailed logging* preference (`*:Debug`) never skews a measurement.

## Baseline, 2026-11-05

The PR #40 build (`main` + opt-in native macros), Vulkan, 0.5x, 1080p/60 Hz, warm caches,
console defaults otherwise. Two runs each, interleaved:

| Run | FPS (weighted) | Median 5 s window | Worst frame ms (median/max) | Device peak MiB | Images peak MiB | Crash |
|---|---|---|---|---|---|---|
| JIT 1 | 23.5 | 23.8 | 203/1012 | 5578 | 2663 | out of device memory at 170 s |
| native 1 | 21.2 | 21.3 | 286/850 | 6140 | 3014 | device lost at 221 s |
| JIT 2 | 25.6 | 26.3 | 202/821 | 6143 | 2499 | device lost at 201 s |
| native 2 | 25.8 | 25.5 | 183/1108 | 5944 | 3012 | out of device memory at 190 s |

- **No regression.** The title runs at 23–26 FPS, the same band as the 25.4/26.8 FPS measured
  on 2026-11-04. The 16.8 FPS reported earlier came from a cold-cache run, and the attract
  scenes differ between runs.
- **Native macros:** no FPS difference at this scale (24.5 vs 23.5, the median of the run
  medians, inside the run-to-run spread).
- **Every run crashed within 170–221 s**, even the unmeasured priming run (at 120 s). Device
  memory peaks at 5.6–6.1 GB while images hold only 2.5–3.0 GB. Guest memory held by the
  sparse backing grows from 1.1 to 4.6 GB in the same pool. Device lost and out of device
  memory both appear once the 12 GB pool is exhausted.

Next: break down the driver's non-VMA memory (`tools/patch-radv-memory-report.py`, Phase 1).
