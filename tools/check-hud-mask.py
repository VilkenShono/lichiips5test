#!/usr/bin/env python3
"""The FPS overlay's selectable fields, size and corner: the line each field mask gives, where the
box goes in pictures of several sizes, the two-glyphs-a-word text both shaders read, and the
places that carry the settings from the launcher to the renderers."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
headless = root / 'headless'
read = lambda name: (headless / name).read_text()

# Both shaders read two 15-bit glyphs to a word, low half first, up to hud.h's kHudTextMax.
frag = read('vulkan_hud.frag')
assert 'glyphs[i >> 1] >> uint((i & 1) * 16)) & 0x7fffu' in frag and 'i < 56' in frag
graphics = read('graphics.cpp')
assert '(glyphs[i>>1]>>uint((i&1)*16))&0x7fffu' in graphics and 'i<56' in graphics
# The Vulkan overlay is placed by PlaceHud and given the rows its cells are laid out for.
draw = read('vulkan_hud_draw.inc')
assert 'Eden::PlaceHud(hud, render_area.width, render_area.height)' in draw
assert 'constants.width = hud_place.cell_rows;' in draw
# The renderers read the fields, size and corner with the session's settings, and the machine's
# numbers once a second with the emulation speed.
assert graphics.count('LoadHudPreferences();') == 1 and 'WantGpuTime();' in graphics
assert graphics.count('MachineNow();') == 2
assert 'hud_fields.load(std::memory_order_relaxed)' in graphics.split('void GraphicsWindow::OnFrameDisplayed()', 1)[1]
# The scheduler's timestamp probe sees what the overlay asks for (hud_gpu_time.h).
prepare = (root / 'tools/prepare-vulkan-port.py').read_text()
assert '#include \\"hud_gpu_time.h\\"' in prepare or '#include "hud_gpu_time.h"' in prepare.replace('\\"', '"')
probe = read('gpu_time_probe.inc')
assert '::Eden::Hud::gpu_time_wanted' in probe and '::Eden::Hud::gpu_busy_ns.fetch_add' in probe
# Settings: stored under the video keys, and the launcher has a row for every field bit.
store = read('settings_store.h')
for key in ('fps_overlay_fields', 'fps_overlay_size', 'fps_overlay_corner'):
    assert store.count(f'"{key}"') >= 2, key
settings_ui = read('eglantineps5/pe/ui/settings.cpp')
rows = settings_ui.split('enum VideoRow : int', 1)[1].split('kVideoRows,', 1)[0]
fields = re.findall(r'^\s*(video_overlay_\w+),', rows, re.M)
assert fields[:2] == ['video_overlay_size', 'video_overlay_corner'] and len(fields) == 2 + 8, fields
assert rows.index('video_overlay_ping') < rows.index('video_frame_gen,'), 'frame generation rows stay last'
services = read('eglantineps5/eden_services.cpp')
for name in ('hud_fields', 'hud_size', 'hud_corner'):
    assert f'result.{name} = saved.{name};' in services and f'value.{name} = preferences.{name};' in services
notices = (root / 'THIRD_PARTY_NOTICES.md').read_text()
assert 'overlay' in notices.split('[ProsperoEden]', 1)[1].split('- **[', 1)[0]

with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'hud_mask.cpp'
    binary = Path(directory) / 'hud_mask'
    source.write_text(r'''#include "hud.h"
#include <cassert>
#include <set>
#include <string_view>
using namespace Eden;
static std::string_view Line(const std::array<char, kHudTextMax + 1>& text) { return text.data(); }
int main() {
    HudClock clock;
    clock.fps = 60;
    clock.worst_ms = 17;
    HudMachine machine;
    machine.cpu = 55;
    machine.gpu = 43;
    machine.memory_free = 4509715661ull;  // 4.2 GiB
    // The default is the line from before there was a choice, with the free memory.
    static_assert(kHudFieldDefault == 0xcf && kHudFieldClassic == 0x8f);
    assert(Line(FormatHudText(clock, clock, 100, "VLK", machine, 0, -1, kHudFieldDefault)) == "VLK F60 S100 W17 M4.2G");
    assert(Line(FormatHudText(clock, clock, 100, "VLK", machine, 0, 42, kHudFieldDefault)) == "VLK F60 S100 W17 M4.2G P42");
    assert(Line(FormatHudText(clock, clock, 100, "VLK", machine, 0, 42, kHudFieldSupported)) ==
           "VLK F60 S100 W17 C55 G43 M4.2G P42");
    // Each field alone, with nothing in front of it.
    const std::pair<uint32_t, std::string_view> alone[] = {
        {kHudFieldBackend, "VLK"}, {kHudFieldFps, "F60"}, {kHudFieldMs, "W17"}, {kHudFieldSpeed, "S100"},
        {kHudFieldCpu, "C55"}, {kHudFieldGpu, "G43"}, {kHudFieldMem, "M4.2G"}, {kHudFieldPing, "P42"}};
    for (const auto& [field, text] : alone)
        assert(Line(FormatHudText(clock, clock, 100, "VLK", machine, 0, 42, field)) == text);
    assert(Line(FormatHudText(clock, clock, 100, "VLK", machine, 0, 42, 0)).empty());
    // Ping only in a room; numbers that cannot be read show as "--".
    assert(Line(FormatHudText(clock, clock, 100, "VLK", machine, 0, -1, kHudFieldPing)).empty());
    assert(Line(FormatHudText(clock, clock, 100, "OGL", HudMachine{}, 0, -1, kHudFieldSupported)) ==
           "OGL F60 S100 W17 C-- G-- M--");
    // With frame generation both rates, still as one field.
    HudClock shown = clock;
    shown.fps = 120;
    clock.fps = 30;
    assert(Line(FormatHudText(clock, shown, 100, "VLK", machine, 119.88, -1, kHudFieldFps | kHudFieldMem)) ==
           "N30 F120 M4.2G");
    // Before the first second of frames.
    clock.fps = -1;
    assert(Line(FormatHudText(clock, shown, 0, "VLK", machine, 0, -1, kHudFieldDefault)) == "VLK F-- S-- W-- M4.2G");
    // However large the numbers, the line fits, and what does not fit is cut whole from the end.
    clock.fps = clock.worst_ms = 1e9;
    shown.fps = 2e9;
    machine.cpu = machine.gpu = 100000;
    machine.memory_free = ~0ull;
    const auto longest = FormatHudText(clock, shown, 1e9, "VLK", machine, 0, 1000000, kHudFieldSupported);
    assert(Line(longest).size() <= kHudTextMax && Line(longest).ends_with(" P9999"));
    assert(Line(FormatHudText(clock, shown, 1e9, "A-VERY-LONG-RENDERER-NAME-THAT-TAKES-MOST-OF-THE-LINE", machine,
                              0, 42, kHudFieldSupported)) == "A-VERY-LONG-RENDERER-NAME-THAT-TAKES-MOST-OF-THE-LINE");
    assert(ValidHudFields(0) && ValidHudFields(0xff) && !ValidHudFields(0x100) && !ValidHudFields(-1));

    // Two glyphs to a word, low half first, and nothing past kHudTextMax.
    const auto packed = HudText("FM");
    assert(packed[0] == (HudGlyph('F') | HudGlyph('M') << 16) && packed[1] == 0);
    const std::string full(kHudTextMax + 4, '8');
    const auto words = HudText(full);
    for (size_t i = 0; i < kHudTextMax; ++i) assert(HudTextGlyph(words, i) == HudGlyph('8'));
    assert(HudTextGlyph(words, kHudTextMax) == 0);
    // Every letter the line uses has a glyph, and none two letters share.
    std::set<uint32_t> distinct;
    for (char c : std::string_view("VLKOGNFSWCMP")) {
        assert(HudGlyph(c) != 0);
        distinct.insert(HudGlyph(c));
    }
    assert(distinct.size() == 12);

    // Where the box goes. At 1x in 1080 rows: 16 in from the corner's edges, 48 high, the text 12
    // in and 14 down, cells of 4 pixels, as before there was a choice.
    clock.fps = 60;
    clock.worst_ms = 17;
    machine = {};
    HudSnapshot hud = MakeHudSnapshot(clock, clock, 100, machine, 0, -1, kHudFieldClassic);
    assert(hud.width == std::string_view("VLK F60 S100 W17").size() * 16 + 24 && hud.x == 0 && hud.y == 0);
    auto place = PlaceHud(hud, 1920, 1080);
    assert(place.shown && place.box_x == 16 && place.box_y == 16 && place.box_w == hud.width && place.box_h == 48);
    assert(place.text_x == 28 && place.text_y == 30 && place.cell_rows == 1080);
    // Each corner, the same distance in from its two edges.
    for (int corner = 0; corner < kHudCorners; ++corner) {
        hud = MakeHudSnapshot(clock, clock, 100, machine, 0, -1, kHudFieldClassic, 0, corner);
        place = PlaceHud(hud, 1920, 1080);
        const bool right = corner == 1 || corner == 3, bottom = corner >= 2;
        assert(place.shown && place.box_x == (right ? 1920 - 16 - place.box_w : 16));
        assert(place.box_y == (bottom ? 1080 - 16 - 48 : 16));
        assert(place.text_x - place.box_x == 12 && place.text_y - place.box_y == 14);
    }
    // The sizes: 1.5x and 2x take the box, the text's offset and the cells that many times over;
    // the distance to the edges stays. In a 2160-row picture everything is twice over again.
    for (int size = 0; size < kHudSizes; ++size) {
        hud = MakeHudSnapshot(clock, clock, 100, machine, 0, -1, kHudFieldClassic, size, 3);
        for (const uint32_t rows : {1080u, 2160u}) {
            const uint32_t columns = rows * 16 / 9, k = rows / 1080;
            place = PlaceHud(hud, columns, rows);
            const uint32_t halves = 2 + size;
            assert(place.shown && place.box_w == hud.width * halves / 2 * k && place.box_h == 24 * halves * k);
            assert(place.box_x + place.box_w == columns - 16 * k && place.box_y + place.box_h == rows - 16 * k);
            assert(place.cell_rows == rows * halves / 2);
            assert(place.text_x == place.box_x + 6 * halves * k && place.text_y == place.box_y + 7 * halves * k);
        }
    }
    // Out-of-range indices are held to the last size and corner.
    hud = MakeHudSnapshot(clock, clock, 100, machine, 0, -1, kHudFieldClassic, 9, 9);
    assert(hud.x == 3 && hud.y == 2);
    // A box wider than the picture is not drawn: everything scales with the picture's height, so
    // a narrow picture is the one a large box may not fit.
    hud = MakeHudSnapshot(clock, clock, 100, machine, 0, -1, kHudFieldSupported, 2);
    assert(hud.width == 28 * 16 + 24 && !PlaceHud(hud, 900, 1080).shown);
    hud.y = 0;
    assert(PlaceHud(hud, 900, 1080).shown);
    assert(!PlaceHud(HudSnapshot{}, 1920, 1080).shown);
    // The longest line still fits a 16:9 picture at 2x.
    clock.fps = clock.worst_ms = 1e9;
    machine.cpu = machine.gpu = 100;
    machine.memory_free = 99ull << 30;
    hud = MakeHudSnapshot(clock, shown, 1e9, machine, 0, 9999, kHudFieldSupported, 2, 1);
    assert(PlaceHud(hud, 1920, 1080).shown);

    // The CPU and GPU shares.
    assert(HudPercent(0, 1000) == 0 && HudPercent(500, 1000) == 50 && HudPercent(1005, 1000) == 100);
    assert(HudPercent(5, 1000) == 1 && HudPercent(4, 1000) == 0 && HudPercent(100, 0) == 0 && HudPercent(-5, 100) == 0);
}
''')
    subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-I' + str(headless), str(source), '-o', str(binary)],
                   check=True)
    subprocess.run([str(binary)], check=True)
print('HUD field masks, bounded lines, packed glyphs, size and corner placement, settings wiring PASS')
