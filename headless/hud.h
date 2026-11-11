// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string_view>
#include "hud_gpu_time.h"

namespace Eden {
// Counts contiguous presentation intervals; loading gaps are never reported as FPS.
struct HudClock {
    double start{-1}, last{-1}, fps{-1}, worst_ms{}, window_worst_ms{};
    unsigned frames{};
    void Present(double now) {
        if (last >= 0 && now - last > 0.5) {
            start = last = now;
            fps = -1;
            worst_ms = 0;
            window_worst_ms = 0;
            frames = 0;
            return;
        }
        if (last >= 0) window_worst_ms = std::max(window_worst_ms, (now - last) * 1000.0);
        last = now;
        if (start < 0) { start = now; return; }
        ++frames;
        if (now - start >= 1.0) {
            fps = frames / (now - start);
            worst_ms = window_worst_ms;
            window_worst_ms = 0;
            frames = 0;
            start = now;
        }
    }
};

// Keep startup work behind the loading screen until presentation is sustained.
struct StartupGate {
    double last{-1}, first{-1};
    unsigned smooth_frames{};
    bool Ready(double now) {
        if (first < 0) first = now;
        smooth_frames = last >= 0 && now > last && now - last <= 0.1 ? smooth_frames + 1 : 0;
        last = now;
        return smooth_frames >= 8 || now - first >= 5.0;
    }
};
// The overlay's font: 3x5 cells, one bit per cell, the top row in the high bits.
inline uint32_t HudGlyph(char c) {
    switch (c) {
    case '0': return 0x7b6f;
    case '1': return 0x2c97;
    case '2': return 0x73e7;
    case '3': return 0x73cf;
    case '4': return 0x5bc9;
    case '5': return 0x79cf;
    case '6': return 0x79ef;
    case '7': return 0x7292;
    case '8': return 0x7bef;
    case '9': return 0x7bcf;
    case 'F': return 0x79a4;
    case 'P': return 0x6ba4;
    case 'S': return 0x79cf;
    case 'L': return 0x4927;
    case 'O': return 0x7b6f;
    case 'A': return 0x2bed;
    case 'D': return 0x6b6e;
    case 'I': return 0x7497;
    case 'N': return 0x5ffd;
    case 'G': return 0x796f;
    case 'V': return 0x5b6a;
    case 'K': return 0x5bad;
    // W is wide at the bottom and M at the top, so the worst frame and the memory read apart.
    case 'W': return 0x5bfd;
    case 'M': return 0x5fed;
    case 'C': return 0x7927;
    case '.': return 0x0002;
    case '-': return 0x01c0;
    default: return 0;
    }
}
// How many characters the overlay's line may have: two 15-bit glyphs to each of a snapshot's
// 28 words (low half first), so the line with every field on still fits in the push constants.
inline constexpr size_t kHudTextMax = 56;
inline std::array<uint32_t, 28> HudText(std::string_view text) {
    std::array<uint32_t, 28> glyphs{};
    for (size_t i = 0; i < text.size() && i < kHudTextMax; ++i)
        glyphs[i / 2] |= HudGlyph(text[i]) << (i % 2 * 16);
    return glyphs;
}
// One glyph of HudText's words, as both shaders read it (vulkan_hud.frag, graphics.cpp DrawHud).
inline uint32_t HudTextGlyph(const std::array<uint32_t, 28>& glyphs, size_t i) {
    return i < kHudTextMax ? (glyphs[i / 2] >> (i % 2 * 16)) & 0x7fffu : 0;
}
// What the overlay's line may say, bit by bit (Settings > Video, settings_store.h's
// fps_overlay_fields). The bits are the ones ProsperoEden's launcher saves for the same pieces,
// so the two read each other's numbers alike; its resolution and per-core bits are not used here.
inline constexpr uint32_t kHudFieldBackend = 1u << 0;  // VLK or OGL
inline constexpr uint32_t kHudFieldFps = 1u << 1;      // F60, or N30 F60 with frame generation
inline constexpr uint32_t kHudFieldMs = 1u << 2;       // W17: the worst frame of the last second
inline constexpr uint32_t kHudFieldSpeed = 1u << 3;    // S100: emulation speed
inline constexpr uint32_t kHudFieldCpu = 1u << 4;      // C55: the busiest emulated core
inline constexpr uint32_t kHudFieldGpu = 1u << 5;      // G43: the GPU's busy share
inline constexpr uint32_t kHudFieldMem = 1u << 6;      // M4.2G: the pool's largest free block
inline constexpr uint32_t kHudFieldPing = 1u << 7;     // P42: in a multiplayer room only
inline constexpr uint32_t kHudFieldCount = 8;
inline constexpr uint32_t kHudFieldSupported = (1u << kHudFieldCount) - 1;
// What the line said before there was a choice, and what a setting that names none starts at:
// that and the free memory. CPU and GPU are off until asked for, as the GPU's share needs the
// scheduler to write timestamps (hud_gpu_time.h).
inline constexpr uint32_t kHudFieldClassic = kHudFieldBackend | kHudFieldFps | kHudFieldMs | kHudFieldSpeed |
                                             kHudFieldPing;
inline constexpr uint32_t kHudFieldDefault = kHudFieldClassic | kHudFieldMem;
inline constexpr bool ValidHudFields(int fields) {
    return fields >= 0 && (static_cast<uint32_t>(fields) & ~kHudFieldSupported) == 0;
}
// The overlay's size (1x, 1.5x, 2x) and the corner it stands in (top left, top right, bottom
// left, bottom right): the launcher's order, settings_store.h's kHudSizeKeys and kHudCornerKeys.
inline constexpr int kHudSizes = 3, kHudCorners = 4;
// What the line says about the machine: ~0u is a percentage that could not be read, a free
// memory of 0 one that could not; the line shows both as "--".
struct HudMachine {
    unsigned cpu = ~0u;              // the busiest emulated core, as a share of one CPU
    unsigned gpu = ~0u;              // the GPU's busy share of the wall clock
    unsigned long long memory_free = 0;  // the direct memory pool's largest free block, in bytes
};
// Work against wall time as a whole percentage, 0 to 100, for the CPU and GPU fields. A thread's
// CPU clock and the monotonic clock are read a moment apart, so a busy core can come out a little
// over its wall time: that is 100.
inline unsigned HudPercent(long long work, long long wall) {
    if (wall <= 0 || work <= 0) return 0;
    if (work >= wall) return 100;
    return static_cast<unsigned>((work * 100 + wall / 2) / wall);
}
// The overlay's snapshot. For the line, `width` is its box's width at 1x in a picture 1080 rows
// high, x the corner and y the size (MakeHudSnapshot); where it is drawn PlaceHud turns them into
// pixels, and the shader is then given the text's origin in x and y and the rows its cells are
// laid out for in `width` (vulkan_hud_draw.inc). The loading screen uses the same words otherwise
// (MakeLoadingSnapshot).
struct HudSnapshot {
    std::array<uint32_t, 28> glyphs{};
    uint32_t width{};
    uint32_t x{}, y{}, loading{};
};
static_assert(sizeof(HudSnapshot) == 128); // Vulkan guarantees at least 128 push-constant bytes.
// What a game's start is doing, for the loading screen (loading_scene.glsl draws it: the steps
// one under the other and a progress bar). main.cpp says which step the start is at; the bar's
// share of each step is an estimate, except while shaders are built, where it is counted. Within
// a step of unknown length the bar creeps towards the step's end and never reaches it.
namespace Loading {
enum class Step : uint32_t { none, game, graphics, shaders, starting };
inline std::atomic<uint32_t> step{0}, built{0}, total{0};
inline std::atomic<int64_t> since{0};  // when the step began, in milliseconds
inline int64_t Now() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline void Set(Step next) {
    if (next <= Step::game) built = total = 0;
    since.store(Now(), std::memory_order_relaxed);
    step.store(static_cast<uint32_t>(next), std::memory_order_relaxed);
}
inline void Shaders(size_t done, size_t of) {
    built.store(static_cast<uint32_t>(done), std::memory_order_relaxed);
    total.store(static_cast<uint32_t>(of), std::memory_order_relaxed);
}
// Where the bar should stand, 0 to 1.
inline double Target(int64_t now) {
    static constexpr double kFrom[] = {0.0, 0.02, 0.25, 0.40, 0.90}, kTo[] = {0.02, 0.25, 0.40, 0.90, 0.99};
    const uint32_t at = std::min<uint32_t>(step.load(std::memory_order_relaxed), 4);
    const double seconds = static_cast<double>(now - since.load(std::memory_order_relaxed)) / 1000.0;
    double part = 1.0 - std::exp(-std::max(seconds, 0.0) / (at == 4 ? 12.0 : 4.0));
    if (at == 3) {
        const uint32_t of = total.load(std::memory_order_relaxed);
        part = of ? std::min(1.0, static_cast<double>(built.load(std::memory_order_relaxed)) / of) : part * 0.1;
    }
    return kFrom[at] + (kTo[at] - kFrom[at]) * part;
}
// What the shader is given (the overlay's 24 words): the step, the progress in thousandths,
// the shaders built and their total, the seconds the step has lasted. The bar moves towards
// its target a little with every picture and never back within one start.
inline std::array<uint32_t, 24> State() {
    static double shown = 0;
    static int64_t last = 0;
    static uint32_t last_step = 0;
    const int64_t now = Now();
    const uint32_t at = step.load(std::memory_order_relaxed);
    if (at < last_step || at == 0) shown = 0;  // a new start
    last_step = at;
    const double elapsed = std::clamp(static_cast<double>(now - last) / 1000.0, 0.0, 0.25);
    last = now;
    shown = std::max(shown, shown + (Target(now) - shown) * (1.0 - std::exp(-elapsed * 6.0)));
    std::array<uint32_t, 24> state{};
    state[0] = at;
    state[1] = static_cast<uint32_t>(std::clamp(shown, 0.0, 1.0) * 1000.0);
    state[2] = built.load(std::memory_order_relaxed);
    state[3] = total.load(std::memory_order_relaxed);
    state[4] = static_cast<uint32_t>(std::clamp<int64_t>((now - since.load(std::memory_order_relaxed)) / 1000, 0, 99999));
    return state;
}
} // namespace Loading
// The loading screen: the shader draws it from the time and that state (loading_scene.glsl).
// `loading` carries the milliseconds since loading began, plus one; x and y carry the size of the
// picture, set where it is drawn (vulkan_hud_draw.inc); the glyphs' words carry the state.
inline HudSnapshot MakeLoadingSnapshot(double seconds) {
    HudSnapshot snapshot{};
    const auto state = Loading::State();
    std::copy(state.begin(), state.end(), snapshot.glyphs.begin());
    snapshot.width = 1920;
    snapshot.x = 1920;
    snapshot.y = 1080;
    snapshot.loading = 1 + static_cast<uint32_t>(std::max(0.0, seconds) * 1000.0);
    return snapshot;
}
// When the next picture of the loading screen is due. With nothing else to do (idle) the GPU
// thread draws one for every display refresh; while it works on the game's own commands it draws
// only a few a second, so the animation never slows the game's start.
struct LoadingPace {
    double next{-1}, last{-1};
    bool Due(double now, bool idle) {
        if (last >= 0 && (idle ? now < next : now - last < 0.1)) return false;
        next = last < 0 || now - next > 0.05 ? now + 1.0 / 60.0 : next + 1.0 / 60.0;
        last = now;
        return true;
    }
};
// Where the line's box goes in a picture `width` x `height`, in pixels. At 1x the box is laid out
// for a picture 1080 rows high: 16 units in from its corner's two edges, 48 high, the text 12 in
// and 14 down, a glyph's cell 4 units; 1.5x and 2x take all but the distance to the edges that
// many times over. `cell_rows` is what the shaders lay the cells out for (a cell is
// 4 * cell_rows / 1080 pixels). `shown` is false where the box does not fit the picture: it is
// then not drawn, as before there was a choice of size.
struct HudPlacement {
    uint32_t box_x{}, box_y{}, box_w{}, box_h{};
    uint32_t text_x{}, text_y{}, cell_rows{};
    bool shown{};
};
inline HudPlacement PlaceHud(const HudSnapshot& hud, uint32_t width, uint32_t height) {
    const uint64_t halves = 2 + std::min<uint32_t>(hud.y, kHudSizes - 1);  // the scale, times two
    const auto units = [height](uint64_t value) { return static_cast<uint32_t>(value * height / 1080); };
    const auto scaled = [&](uint64_t value) { return units(value * halves / 2); };
    HudPlacement place;
    const uint32_t margin = units(16);
    place.box_w = scaled(hud.width);
    place.box_h = scaled(48);
    place.cell_rows = static_cast<uint32_t>(uint64_t{height} * halves / 2);
    place.shown = hud.width != 0 && uint64_t{place.box_w} + margin <= width &&
                  uint64_t{place.box_h} + margin <= height;
    if (!place.shown) return place;
    const bool right = (hud.x & 1) != 0, bottom = (hud.x & 2) != 0;
    place.box_x = right ? width - margin - place.box_w : margin;
    place.box_y = bottom ? height - margin - place.box_h : margin;
    place.text_x = place.box_x + scaled(12);
    place.text_y = place.box_y + scaled(14);
    return place;
}
// The overlay's line: "VLK F60 S100 W17 C55 G43 M4.2G P42", each piece as `fields` asks.
// N is the rate the guest itself produces; F is the rate the display shows. They are the same
// until frame generation is on, and the overlay then keeps its usual text (F alone). With frame
// generation F is counted from every frame handed to the present manager (CountPresentedFrame():
// the frames it adds do not go through OnFrameDisplayed(), which runs once per guest frame), and
// never reads above `refresh`, the output's own rate: a display shows no more than that, however
// many frames it is handed. refresh 0: not known, no limit. M is what is left of the memory pool
// in one block, the number that ends a session when it runs out (performance.h, kShortMemory);
// P shows only in a multiplayer room (ping_ms >= 0). Pieces that do not fit are cut, the last
// first.
inline std::array<char, kHudTextMax + 1> FormatHudText(const HudClock& clock, const HudClock& output,
                                                       double speed, const char* backend,
                                                       const HudMachine& machine, double refresh,
                                                       int ping_ms, uint32_t fields) {
    std::array<char, kHudTextMax + 1> text{};
    size_t used = 0;
    // Every piece goes in whole or not at all, after a space unless it is the first; nothing goes
    // in after a piece that did not fit.
    const auto add = [&](const char* piece) {
        const size_t length = std::strlen(piece), need = length + (used ? 1 : 0);
        if (used + need > kHudTextMax) {
            used = kHudTextMax + 1;
            return;
        }
        if (used) text[used++] = ' ';
        std::memcpy(text.data() + used, piece, length);
        used += length;
    };
    char piece[32];
    if (fields & kHudFieldBackend) add(backend);
    const bool known = clock.fps >= 0;
    if (fields & kHudFieldFps) {
        const double shown = !known || output.fps < 0 ? clock.fps
                                                      : refresh > 0 ? std::min(output.fps, refresh) : output.fps;
        if (!known)
            std::snprintf(piece, sizeof(piece), "F--");
        else if (shown < clock.fps + 1.5)
            std::snprintf(piece, sizeof(piece), "F%.0f", std::min(clock.fps, 9999.0));
        else
            std::snprintf(piece, sizeof(piece), "N%.0f F%.0f", std::min(clock.fps, 9999.0), std::min(shown, 9999.0));
        add(piece);
    }
    if (fields & kHudFieldSpeed) {
        if (known) std::snprintf(piece, sizeof(piece), "S%.0f", std::clamp(speed, 0.0, 9999.0));
        else std::snprintf(piece, sizeof(piece), "S--");
        add(piece);
    }
    if (fields & kHudFieldMs) {
        if (known) std::snprintf(piece, sizeof(piece), "W%.0f", std::min(clock.worst_ms, 9999.0));
        else std::snprintf(piece, sizeof(piece), "W--");
        add(piece);
    }
    if (fields & kHudFieldCpu) {
        if (machine.cpu != ~0u) std::snprintf(piece, sizeof(piece), "C%u", std::min(machine.cpu, 999u));
        else std::snprintf(piece, sizeof(piece), "C--");
        add(piece);
    }
    if (fields & kHudFieldGpu) {
        if (machine.gpu != ~0u) std::snprintf(piece, sizeof(piece), "G%u", std::min(machine.gpu, 999u));
        else std::snprintf(piece, sizeof(piece), "G--");
        add(piece);
    }
    if (fields & kHudFieldMem) {
        if (machine.memory_free != 0)
            std::snprintf(piece, sizeof(piece), "M%.1fG",
                          std::min(static_cast<double>(machine.memory_free) / 1073741824.0, 99.9));
        else
            std::snprintf(piece, sizeof(piece), "M--");
        add(piece);
    }
    if ((fields & kHudFieldPing) && ping_ms >= 0) {
        std::snprintf(piece, sizeof(piece), "P%d", std::min(ping_ms, 9999));
        add(piece);
    }
    return text;
}
// What the line said before there was a choice of fields: the callers and checks that predate it.
inline std::array<char, kHudTextMax + 1> FormatHudText(const HudClock& clock, const HudClock& output,
                                                       double speed, const char* backend, double refresh = 0,
                                                       int ping_ms = -1) {
    return FormatHudText(clock, output, speed, backend, HudMachine{}, refresh, ping_ms, kHudFieldClassic);
}
// The line and where it goes: `size` and `corner` are the launcher's indices (kHudSizes,
// kHudCorners), carried to PlaceHud in y and x.
inline HudSnapshot MakeHudSnapshot(const HudClock& clock, const HudClock& output, double speed,
                                   const HudMachine& machine, double refresh, int ping_ms, uint32_t fields,
                                   int size = 0, int corner = 0) {
    const auto text = FormatHudText(clock, output, speed, "VLK", machine, refresh, ping_ms, fields);
    const std::string_view value{text.data()};
    // A line with every field off still keeps the box, empty, so the overlay's switch shows it is on.
    HudSnapshot hud{HudText(value), static_cast<uint32_t>(value.size() * 16 + 24)};
    hud.x = static_cast<uint32_t>(std::clamp(corner, 0, kHudCorners - 1));
    hud.y = static_cast<uint32_t>(std::clamp(size, 0, kHudSizes - 1));
    return hud;
}
inline HudSnapshot MakeHudSnapshot(const HudClock& clock, const HudClock& output, double speed,
                                   double refresh = 0, int ping_ms = -1) {
    return MakeHudSnapshot(clock, output, speed, HudMachine{}, refresh, ping_ms, kHudFieldClassic);
}
// The OpenGL renderer has no frame generation: what it presents is the guest's own rate, so both
// numbers come from one clock. Callers that cannot have an output clock use these.
inline std::array<char, kHudTextMax + 1> FormatHudText(const HudClock& clock, double speed, const char* backend,
                                                       const HudMachine& machine, int ping_ms, uint32_t fields) {
    return FormatHudText(clock, clock, speed, backend, machine, 0, ping_ms, fields);
}
inline std::array<char, kHudTextMax + 1> FormatHudText(const HudClock& clock, double speed, const char* backend,
                                                       int ping_ms = -1) {
    return FormatHudText(clock, clock, speed, backend, 0, ping_ms);
}
inline HudSnapshot MakeHudSnapshot(const HudClock& clock, double speed) {
    return MakeHudSnapshot(clock, clock, speed);
}
// Every frame handed to the present manager, the guest's own and each one frame generation adds,
// so the HUD's F measures the output and not just the guest (graphics.cpp).
void CountPresentedFrame();
// Read on the renderer thread; the scheduler captures the returned value per frame.
HudSnapshot GetVulkanHud();
} // namespace Eden
