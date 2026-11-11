// EglantinePS5 - The launcher's built-in themes and accent presets, and which are in use.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Adapted from ProsperoEden's launcher themes (GPL-3.0-or-later; THIRD_PARTY_NOTICES.md).

#include "pe/ui/theme.hpp"

#include "pe/core/strings.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace pe::ui
{

namespace
{

constexpr Color kBlackInk{0.0f, 0.0f, 0.0f, 1.0f};
constexpr Color kWhiteInk{1.0f, 1.0f, 1.0f, 1.0f};

Color rgb(std::uint32_t hex)
{
    return Color::rgb(hex);
}

// The roles that follow the accent, for a theme that does not set them itself and for every
// accent preset.
void derive_accent_roles(Theme &t)
{
    t.toggle_end = gfx::mix(t.accent, t.accent_deep, 0.45f);
    t.scroll_thumb = t.accent_pale;
    t.hc_focus_edge = gfx::mix(t.accent_pale, kWhiteInk, 0.3f);
}

// The roles a theme other than Eglantine leaves to its main ones: every one of them is a mix of
// colours it set.
void derive_roles(Theme &t)
{
    t.veil = gfx::mix(t.scrim, kBlackInk, 0.4f);
    t.list_row = t.row;
    t.list_row_edge = t.row_edge;
    t.list_row_focus = t.row_focus;
    t.button_fill = t.title;
    t.tile_fill = t.title;
    t.plate_focus = gfx::mix(t.row, t.row_focus, 0.4f);
    t.inset = gfx::mix(t.panel, t.base, 0.3f);
    t.status_panel = t.panel;
    t.cover_top = t.glass;
    t.cover_bottom = t.panel;
    t.divider = t.rule;
    t.toggle_track = gfx::mix(t.row, t.row_edge, 0.15f);
    t.level_track = gfx::mix(t.row, t.row_edge, 0.2f);
    t.scroll_track = t.rule;
    t.controller = t.title;
    t.hc_panel = gfx::mix(t.base, kBlackInk, 0.3f);
    t.hc_panel_edge = t.meta;
    t.hc_row = gfx::mix(t.panel, t.row, 0.4f);
    t.hc_row_edge = t.faint;
    t.hc_focus = t.row_focus;
    t.note = t.copy;
    t.row_name = t.value;
    t.folder = t.body;
    t.kicker = t.body;
    t.caption = t.muted;
    t.clock = t.meta;
    t.detail = t.muted;
    t.nav = t.label;
    t.tile_title = t.body;
    derive_accent_roles(t);
}

// Eglantine: dark rose glass and petal pink. The launcher's own look, the one a new install uses;
// every role is set, to the colours the launcher had before themes.
Theme eglantine()
{
    Theme t;
    t.id = "eglantine";
    t.name = "Eglantine";
    t.summary = TR("Dark rose glass and petal pink.");

    t.base = rgb(0x0a0606);
    t.scrim = rgb(0x080102);
    t.veil = rgb(0x070203);
    t.glass = rgb(0x221618);
    t.panel = rgb(0x170b0d);
    t.panel_edge = rgb(0x8e757b);
    t.row = rgb(0x241719);
    t.row_edge = rgb(0x82676e);
    t.row_focus = rgb(0x44292e);
    t.list_row = rgb(0x231517);
    t.list_row_edge = rgb(0x82676d);
    t.list_row_focus = rgb(0x442a2f);
    t.button_fill = rgb(0xede4e6);
    t.tile_fill = rgb(0xf7edef);
    t.plate_focus = rgb(0x2c1c1f);
    t.inset = rgb(0x180d0f);
    t.status_panel = rgb(0x160a0c);
    t.cover_top = rgb(0x241618);
    t.cover_bottom = rgb(0x150c0e);
    t.divider = rgb(0x6d585d);

    t.toggle_track = rgb(0x332427);
    t.toggle_end = rgb(0xae526b);
    t.level_track = rgb(0x3b2b2e);
    t.scroll_track = rgb(0x62494f);
    t.scroll_thumb = rgb(0xe8aabe);
    t.controller = rgb(0xf7eff1);

    t.hc_panel = rgb(0x0b0506);
    t.hc_panel_edge = rgb(0xc9b4ba);
    t.hc_row = rgb(0x1a0f11);
    t.hc_row_edge = rgb(0xa89096);
    t.hc_focus = rgb(0x3a1b21);
    t.hc_focus_edge = rgb(0xffc4d7);

    // The rose's petal-tip pink to deep rose, left to right.
    t.accent = rgb(0xe23b60);
    t.accent_deep = rgb(0x7a1f3d);
    t.accent_pale = rgb(0xe8a6bc);
    t.on_accent = rgb(0x201214);
    t.highlight = rgb(0xffb3c4);

    t.text = rgb(0xf5f0f1);
    t.title = rgb(0xfff2f5);
    t.value = rgb(0xf4e9ed);
    t.body = rgb(0xe8d7dc);
    t.copy = rgb(0xd0bdc2);
    t.meta = rgb(0xc6b5b9);
    t.label = rgb(0xbdaaaf);
    t.muted = rgb(0xb8aaad);
    t.faint = rgb(0x9e8c90);
    t.warning = rgb(0xe8b39a);
    t.rule = rgb(0x6b5358);
    t.note = rgb(0xcbb9be);
    t.row_name = rgb(0xf5e9ed);
    t.folder = rgb(0xd6bdc4);
    t.kicker = rgb(0xd2c6c9);
    t.caption = rgb(0xac9ea1);
    t.clock = rgb(0xcdc1c4);
    t.detail = rgb(0xb8abae);
    t.nav = rgb(0xbbafb2);
    t.tile_title = rgb(0xe1d7d9);
    return t;
}

// Canopy: a tropical dusk, dark green glass and lime.
Theme canopy()
{
    Theme t;
    t.id = "canopy";
    t.name = "Canopy";
    t.summary = TR("Tropical dusk, dark green glass and lime.");

    t.base = rgb(0x06090a);
    t.scrim = rgb(0x010806);
    t.glass = rgb(0x16221d);
    t.panel = rgb(0x0b1713);
    t.panel_edge = rgb(0x768e75);
    t.row = rgb(0x17241e);
    t.row_edge = rgb(0x6a8267);
    t.row_focus = rgb(0x294433);

    t.accent = rgb(0xa9db63);
    t.accent_deep = rgb(0x245d4a);
    t.accent_pale = rgb(0xdfe8a6);
    t.on_accent = rgb(0x0b1713);
    t.highlight = rgb(0xffd76a);

    t.text = rgb(0xf0f5f2);
    t.title = rgb(0xfffcef);
    t.value = rgb(0xf2f4e9);
    t.body = rgb(0xe2e8d7);
    t.copy = rgb(0xc5d0bd);
    t.meta = rgb(0xb7c6b5);
    t.label = rgb(0xaebdaa);
    t.muted = rgb(0xaab8ac);
    t.faint = rgb(0x8c9e90);
    t.warning = rgb(0xe8b39a);
    t.rule = rgb(0x536b55);
    derive_roles(t);
    return t;
}

// Slate: neutral glass, clean and still.
Theme slate()
{
    Theme t;
    t.id = "slate";
    t.name = "Slate";
    t.summary = TR("Neutral glass, clean and still.");

    t.base = rgb(0x101012);
    t.scrim = rgb(0x080809);
    t.glass = rgb(0x1c1c20);
    t.panel = rgb(0x141416);
    t.panel_edge = rgb(0x3a3a3e);
    t.row = rgb(0x1e1e22);
    t.row_edge = rgb(0x34343a);
    t.row_focus = rgb(0x2c2c32);

    t.accent = rgb(0xc0bbb6);
    t.accent_deep = rgb(0x3a3836);
    t.accent_pale = rgb(0xdedbd8);
    t.on_accent = rgb(0x101012);
    t.highlight = rgb(0xe8e4e0);

    t.text = rgb(0xeae8e6);
    t.title = rgb(0xf2f0ee);
    t.value = rgb(0xe6e4e2);
    t.body = rgb(0xd0cecc);
    t.copy = rgb(0xb0aeac);
    t.meta = rgb(0x98969a);
    t.label = rgb(0x88868a);
    t.muted = rgb(0x78767a);
    t.faint = rgb(0x585660);
    t.warning = rgb(0xe0685e);
    t.rule = rgb(0x34343a);
    derive_roles(t);
    return t;
}

// ---- accent presets: named colour sets a player can pick for a theme ----
// The first of each theme's is its own colours, stored as "" in the settings file.

const AccentPreset kEglantineAccents[] = {
    {"rose", "Rose", rgb(0xe23b60), rgb(0x7a1f3d), rgb(0xe8a6bc), rgb(0x201214), rgb(0xffb3c4)},
    {"coral", "Coral", rgb(0xe8705a), rgb(0x6a2a20), rgb(0xf0b8a8), rgb(0x1e1210), rgb(0xffc8b8)},
    {"amber", "Amber", rgb(0xe0a848), rgb(0x5a4018), rgb(0xf0d090), rgb(0x1a140a), rgb(0xf5dca0)},
    {"lilac", "Lilac", rgb(0xb486e0), rgb(0x46286e), rgb(0xd8c0f0), rgb(0x161020), rgb(0xe4d4f8)},
    {"ocean", "Ocean", rgb(0x58a8d8), rgb(0x183a58), rgb(0xa0d0f0), rgb(0x0a1018), rgb(0xb8e0f8)},
    {"mint", "Mint", rgb(0x6ecaa0), rgb(0x1e4a38), rgb(0xb0e8cc), rgb(0x0a1410), rgb(0xc8f0d8)},
    {"silver", "Silver", rgb(0xc0bbb6), rgb(0x3a3836), rgb(0xdedbd8), rgb(0x101012), rgb(0xe8e4e0)},
};

const AccentPreset kCanopyAccents[] = {
    {"lime", "Lime", rgb(0xa9db63), rgb(0x245d4a), rgb(0xdfe8a6), rgb(0x0b1713), rgb(0xffd76a)},
    {"gold", "Gold", rgb(0xe0c050), rgb(0x4a3a18), rgb(0xf0dda0), rgb(0x0b1410), rgb(0xffeaa0)},
    {"ember", "Ember", rgb(0xe08850), rgb(0x4a2818), rgb(0xf0c4a0), rgb(0x0e100a), rgb(0xffd4a0)},
    {"teal", "Teal", rgb(0x50c8b0), rgb(0x184a40), rgb(0xa0e8d8), rgb(0x0a1210), rgb(0xb0f0e0)},
    {"sakura", "Sakura", rgb(0xe890a8), rgb(0x4a2030), rgb(0xf0c8d4), rgb(0x100a0c), rgb(0xf8d8e0)},
    {"ocean", "Ocean", rgb(0x58a8d8), rgb(0x183a58), rgb(0xa0d0f0), rgb(0x0a1018), rgb(0xb8e0f8)},
    {"violet", "Violet", rgb(0xa080d0), rgb(0x342060), rgb(0xccb8e8), rgb(0x0c0a14), rgb(0xdcc8f0)},
};

const AccentPreset kSlateAccents[] = {
    {"silver", "Silver", rgb(0xc0bbb6), rgb(0x3a3836), rgb(0xdedbd8), rgb(0x101012), rgb(0xe8e4e0)},
    {"ice", "Ice", rgb(0x7ec8e3), rgb(0x1c4966), rgb(0xb8e0f0), rgb(0x0a1418), rgb(0xd0ecf8)},
    {"rose", "Rose", rgb(0xe88ca0), rgb(0x5c2232), rgb(0xf2c0cc), rgb(0x120a0c), rgb(0xf5d4dc)},
    {"amber", "Amber", rgb(0xe0a848), rgb(0x5a4018), rgb(0xf0d090), rgb(0x121008), rgb(0xf5dca0)},
    {"mint", "Mint", rgb(0x6ecaa0), rgb(0x1e4a38), rgb(0xb0e8cc), rgb(0x0a1410), rgb(0xc8f0d8)},
    {"lilac", "Lilac", rgb(0xb098d8), rgb(0x3c2868), rgb(0xd4c4ec), rgb(0x0e0a14), rgb(0xe0d4f0)},
    {"sky", "Sky", rgb(0x60a8e0), rgb(0x1a3a5c), rgb(0xa8d0f0), rgb(0x0a1018), rgb(0xc0dcf5)},
};

struct Store
{
    // The first is the default: a settings file without a theme, or with one this build has not,
    // shows the launcher as it always looked.
    std::array<Theme, 3> all{eglantine(), canopy(), slate()};
    int index = 0;
    int accent = 0;
    Theme active = all[0];
};

Store &store()
{
    static Store value;
    return value;
}

std::span<const AccentPreset> presets_for(int theme)
{
    switch (theme)
    {
    case 0:
        return kEglantineAccents;
    case 1:
        return kCanopyAccents;
    case 2:
        return kSlateAccents;
    default:
        return {};
    }
}

} // namespace

const Theme &th()
{
    return store().active;
}

std::span<const Theme> themes()
{
    return store().all;
}

int theme_index()
{
    return store().index;
}

bool use_theme(std::string_view id)
{
    Store &s = store();
    for (std::size_t i = 0; i < s.all.size(); ++i)
    {
        if (id == s.all[i].id)
        {
            s.index = static_cast<int>(i);
            s.active = s.all[i];
            s.accent = 0;
            return true;
        }
    }
    return false;
}

std::span<const AccentPreset> accent_presets()
{
    return presets_for(store().index);
}

int accent_index()
{
    return store().accent;
}

void use_accent(std::string_view id)
{
    Store &s = store();
    s.accent = 0;
    s.active = s.all[static_cast<std::size_t>(s.index)];
    // The first preset is the theme's own colours: nothing is laid over them.
    const std::span<const AccentPreset> presets = presets_for(s.index);
    for (std::size_t i = 1; i < presets.size(); ++i)
    {
        if (id != presets[i].id)
            continue;
        s.accent = static_cast<int>(i);
        s.active.accent = presets[i].accent;
        s.active.accent_deep = presets[i].accent_deep;
        s.active.accent_pale = presets[i].accent_pale;
        s.active.on_accent = presets[i].on_accent;
        s.active.highlight = presets[i].highlight;
        derive_accent_roles(s.active);
        return;
    }
}

} // namespace pe::ui
