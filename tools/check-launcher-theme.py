#!/usr/bin/env python3
# EglantinePS5 - The launcher's screens take every colour from the theme in use.
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
# Adapted from ProsperoEden's tools/check-launcher-theme.py (GPL-3.0-or-later).
"""check-launcher-theme.py

A theme fills colour roles (pe/ui/theme.hpp, docs/THEMES.md); a screen that writes a colour of its
own would keep that colour in every theme. This fails when

  - a file of the launcher's screens (headless/eglantineps5/pe/ui, host) other than theme.cpp
    writes a colour as a number (Color::rgb(0x...)) on a line not marked "theme: fixed", or names
    one of the constants the themes replaced (theme::k...),
  - the Eglantine theme is not the first (the default), or its colours are not the rose look the
    launcher had before themes,
  - the default theme of the settings file (settings_store.h, services.hpp) is not Eglantine,
  - the console build does not compile theme.cpp, or the launcher depends on the ps5-homebrew-ui
    kit or ProsperoEden's data folder,
  - theme.cpp, built and run on this machine, leaves a role of a theme unset, or picks themes and
    accent presets other than as theme.hpp says.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "headless/eglantineps5"
SCREENS = [LAUNCHER / "pe/ui", LAUNCHER / "host"]
THEME_HPP = LAUNCHER / "pe/ui/theme.hpp"
THEME_CPP = LAUNCHER / "pe/ui/theme.cpp"

# The launcher's look before themes: Eglantine keeps every one of these.
ROSE = {
    "base": 0x0a0606, "scrim": 0x080102, "glass": 0x221618, "panel": 0x170b0d,
    "panel_edge": 0x8e757b, "row": 0x241719, "row_edge": 0x82676e, "row_focus": 0x44292e,
    "accent": 0xe23b60, "accent_deep": 0x7a1f3d, "accent_pale": 0xe8a6bc, "highlight": 0xffb3c4,
    "text": 0xf5f0f1, "title": 0xfff2f5, "value": 0xf4e9ed, "body": 0xe8d7dc, "copy": 0xd0bdc2,
    "meta": 0xc6b5b9, "label": 0xbdaaaf, "muted": 0xb8aaad, "faint": 0x9e8c90,
    "warning": 0xe8b39a, "rule": 0x6b5358,
    # Written as numbers in the screens before themes, now roles.
    "note": 0xcbb9be, "row_name": 0xf5e9ed, "folder": 0xd6bdc4, "on_accent": 0x201214,
    "veil": 0x070203, "inset": 0x180d0f, "divider": 0x6d585d, "list_row": 0x231517,
    "list_row_edge": 0x82676d, "list_row_focus": 0x442a2f, "button_fill": 0xede4e6,
    "tile_fill": 0xf7edef, "plate_focus": 0x2c1c1f, "hc_panel": 0x0b0506,
    "hc_panel_edge": 0xc9b4ba, "hc_row": 0x1a0f11, "hc_row_edge": 0xa89096, "hc_focus": 0x3a1b21,
    "hc_focus_edge": 0xffc4d7, "cover_top": 0x241618, "cover_bottom": 0x150c0e,
    "controller": 0xf7eff1, "toggle_track": 0x332427, "toggle_end": 0xae526b,
    "level_track": 0x3b2b2e, "scroll_track": 0x62494f, "scroll_thumb": 0xe8aabe,
    "status_panel": 0x160a0c, "kicker": 0xd2c6c9, "caption": 0xac9ea1, "clock": 0xcdc1c4,
    "detail": 0xb8abae, "nav": 0xbbafb2, "tile_title": 0xe1d7d9,
}
ROSE_SIZES = {"size_display": 48.0, "size_lead": 40.0, "size_brand": 36.0, "size_heading": 32.0,
              "size_clock": 28.0, "size_text": 24.0, "size_small": 20.0}
ROSE_MOTION = {"focus_spring": 20.0, "cursor_spring": 26.0, "scroll_spring": 16.0,
               "screen_seconds": 0.30, "launch_seconds": 0.95}


def theme_fields(header):
    body = header[header.index("struct Theme"):header.index("};", header.index("struct Theme"))]
    colours = re.findall(r"^\s*Color (\w+);", body, re.M)
    numbers = dict((name, float(value)) for name, value in
                   re.findall(r"^\s*float (\w+) = ([0-9.]+)f;", body, re.M))
    return colours, numbers


def function_body(source, name):
    start = source.index(f"\nTheme {name}()")
    return source[start:source.index("\n}\n", start)]


def static_checks(problems):
    for folder in SCREENS:
        for source in sorted(folder.glob("*.[ch]pp")):
            if source == THEME_CPP:
                continue
            for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
                where = f"{source.relative_to(ROOT)}:{number}"
                if re.search(r"Color::rgb\(\s*0x", line) and "theme: fixed" not in line:
                    problems.append(f"{where}: a colour written as a number; name its role (th().accent, ...)")
                if re.search(r"\btheme::k[A-Z]", line):
                    problems.append(f"{where}: a constant the themes replaced; use th()")
                if "hui::" in line or "ps5-homebrew-ui" in line:
                    problems.append(f"{where}: the launcher does not use the ps5-homebrew-ui kit")

    header = THEME_HPP.read_text(encoding="utf-8")
    colours, numbers = theme_fields(header)
    missing = sorted(set(ROSE) - set(colours))
    if missing:
        problems.append(f"theme.hpp: no role for {', '.join(missing)}")
    for name, value in {**ROSE_SIZES, **ROSE_MOTION}.items():
        if abs(numbers.get(name, -1.0) - value) > 1e-6:
            problems.append(f"theme.hpp: {name} is not {value} by default")

    source = THEME_CPP.read_text(encoding="utf-8")
    order = re.search(r"std::array<Theme, \d+> all\{(\w+)\(\)", source)
    if not order or order.group(1) != "eglantine":
        problems.append("theme.cpp: Eglantine is not the first theme (the default)")
    rose = function_body(source, "eglantine")
    if "derive_roles" in rose:
        problems.append("theme.cpp: Eglantine sets its roles itself, none derived")
    set_values = dict((name, int(value, 16)) for name, value in
                      re.findall(r"t\.(\w+) = rgb\((0x[0-9a-fA-F]{6})\);", rose))
    for name in colours:
        if name not in set_values:
            problems.append(f"theme.cpp: Eglantine does not set {name}")
        elif name in ROSE and set_values[name] != ROSE[name]:
            problems.append(f"theme.cpp: Eglantine's {name} is {set_values[name]:06x}, not the rose look's {ROSE[name]:06x}")
    if re.search(r"t\.(size_|\w+_spring|\w+_seconds)", rose):
        problems.append("theme.cpp: Eglantine keeps the launcher's type sizes and motion")
    if not re.search(r'\bt\.id = "eglantine";', rose):
        problems.append('theme.cpp: Eglantine\'s id is not "eglantine"')

    store = (ROOT / "headless/settings_store.h").read_text(encoding="utf-8")
    if 'kDefaultLauncherTheme = "eglantine"' not in store:
        problems.append("settings_store.h: the default launcher theme is not eglantine")
    if '"/launcher/theme"' not in store or '"/launcher/accent"' not in store:
        problems.append("settings_store.h: /launcher/theme and /launcher/accent are not read")
    services = (LAUNCHER / "pe/ui/services.hpp").read_text(encoding="utf-8")
    if 'std::string theme = "eglantine";' not in services:
        problems.append("services.hpp: Preferences::theme does not default to eglantine")
    if "pe/ui/theme.cpp" not in (ROOT / "headless/CMakeLists.txt").read_text(encoding="utf-8"):
        problems.append("headless/CMakeLists.txt does not compile pe/ui/theme.cpp")
    for path in [*LAUNCHER.rglob("*.[ch]pp"), ROOT / "headless/settings_store.h"]:
        if "/data/prosperoeden" in path.read_text(encoding="utf-8", errors="replace"):
            problems.append(f"{path.relative_to(ROOT)}: names ProsperoEden's data folder")
    return colours


HARNESS = r'''
#include "pe/ui/theme.hpp"
#include <cstdio>
#include <set>
#include <string>
using namespace pe::ui;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #x); ++failures; } } while (0)
static bool same(const Color &a, const Color &b)
{
    return a.r == b.r && a.g == b.g && a.b == b.b && a.a == b.a;
}
static bool unset(const Color &c)
{
    return c.r == 0.0f && c.g == 0.0f && c.b == 0.0f && c.a == 1.0f;
}
static void every_role(const Theme &t)
{
@ROLES@
}
int main()
{
    CHECK(std::string{th().id} == "eglantine");
    CHECK(theme_index() == 0 && accent_index() == 0);
    std::set<std::string> ids;
    for (const Theme &t : themes())
    {
        every_role(t);
        CHECK(ids.insert(t.id).second);
        CHECK(*t.name != 0 && *t.summary != 0);
    }
    CHECK(themes().size() >= 2);
    for (const Theme &t : themes())
    {
        CHECK(use_theme(t.id));
        CHECK(accent_index() == 0);
        const auto presets = accent_presets();
        CHECK(presets.size() >= 2);
        // The first preset is the theme's own colours.
        CHECK(same(presets[0].accent, t.accent) && same(presets[0].accent_pale, t.accent_pale));
        std::set<std::string> accents;
        for (const AccentPreset &p : presets)
            CHECK(accents.insert(p.id).second);
        use_accent(presets[1].id);
        CHECK(accent_index() == 1 && same(th().accent, presets[1].accent));
        CHECK(same(th().panel, t.panel)); // an accent changes the accent roles only
        use_accent(presets[0].id);
        CHECK(accent_index() == 0 && same(th().accent, t.accent) && same(th().toggle_end, t.toggle_end));
        use_accent(presets[1].id);
        use_accent("");
        CHECK(accent_index() == 0 && same(th().scroll_thumb, t.scroll_thumb));
        use_accent("no-such-colour");
        CHECK(accent_index() == 0 && same(th().accent, t.accent));
    }
    CHECK(use_theme("slate"));
    use_accent("ice");
    CHECK(!use_theme("no-such-theme"));
    CHECK(std::string{th().id} == "slate" && accent_index() == 1);
    CHECK(use_theme("eglantine") && accent_index() == 0);
    CHECK(same(th().accent, Color::rgb(0xe23b60)));
    if (failures == 0)
        std::printf("theme.cpp: %zu themes, every role set\n", themes().size());
    return failures == 0 ? 0 : 1;
}
'''


def run_harness(colours, problems):
    compiler = next((c for c in ("clang++-18", "clang++", "g++", "c++") if shutil.which(c)), None)
    if compiler is None:
        print("check-launcher-theme: no C++ compiler; theme.cpp not run", file=sys.stderr)
        return
    roles = "\n".join(f"    CHECK(!unset(t.{name}));" for name in colours)
    with tempfile.TemporaryDirectory(prefix="launcher-theme-") as scratch:
        harness = Path(scratch) / "theme_check.cpp"
        harness.write_text(HARNESS.replace("@ROLES@", roles), encoding="utf-8")
        binary = Path(scratch) / "theme_check"
        built = subprocess.run([compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror", f"-I{LAUNCHER}",
                                str(harness), str(THEME_CPP), "-o", str(binary)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            problems.append("theme.cpp does not build on this machine:\n" + built.stderr)
            return
        ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
        sys.stdout.write(ran.stdout)
        if ran.returncode != 0:
            problems.append("theme.cpp's themes do not behave as theme.hpp says")


def main():
    problems = []
    colours = static_checks(problems)
    run_harness(colours, problems)
    for problem in problems:
        print(f"check-launcher-theme: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("check-launcher-theme: the screens name roles, and Eglantine is the default rose look")
    return 0


if __name__ == "__main__":
    sys.exit(main())
