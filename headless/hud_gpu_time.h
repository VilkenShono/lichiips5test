// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <atomic>

// What the overlay's GPU field reads (hud.h, HudMachine::gpu). The Vulkan scheduler's timestamp
// probe (gpu_time_probe.inc) is a development tool that is off in a normal session; the overlay
// turns it on only while it shows the GPU field, so no session pays for timestamps it does not
// show. A header of its own because the scheduler that writes these is built without the rest of
// the overlay (tools/prepare-vulkan-port.py includes it there).
namespace Eden::Hud {
inline std::atomic<bool> gpu_time_wanted{false};
// The GPU's busy nanoseconds summed over every command buffer it has run, and how many results
// that is: the overlay takes the rise of the first against the wall clock. Never reset within the
// process, so a renderer restart does not make the share jump backwards.
inline std::atomic<unsigned long long> gpu_busy_ns{0}, gpu_results{0};
// The driver gave up on timestamps (no timestamp support, or results stopped arriving): "--".
inline std::atomic<bool> gpu_time_failed{false};
} // namespace Eden::Hud
