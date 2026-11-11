// EglantinePS5 - Launcher themes: colour roles, type sizes and motion, and which theme is in use.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The theme-as-data design follows ProsperoEden's launcher themes (GPL-3.0-or-later), adapted to
// this launcher's screens (THIRD_PARTY_NOTICES.md).

#pragma once

#include "pe/gfx/draw_list.hpp"

#include <algorithm>
#include <span>
#include <string_view>

namespace pe::ui
{

using gfx::Align;
using gfx::Color;
using gfx::Rect;

// A theme is data: what the launcher's screens are painted with. The screens name roles (accent,
// panel, title), never a hue, and a theme fills every role. It does not move anything: where the
// panels, rows and lists are is the launcher's. docs/THEMES.md describes the roles.
struct Theme
{
    // ---- identity ----
    const char *id = "";      // in the settings file (/launcher/theme)
    const char *name = "";    // as Settings shows it (a name: not translated)
    const char *summary = ""; // one line about it (English; marked with TR() where it is set)

    // ---- colour: surfaces ----
    Color base;       // behind everything, where the artwork does not reach
    Color scrim;      // what dims the artwork behind screens and dialogs
    Color veil;       // the darkest dimming: over the whole screen, under overlays
    Color glass;      // panels over the artwork (home)
    Color panel;      // screens' panels and dialogs
    Color panel_edge; // their hairline
    Color row;        // a control at rest
    Color row_edge;
    Color row_focus;  // under the highlight
    Color list_row;   // a row of a long list (library, folders, languages), and key caps
    Color list_row_edge;
    Color list_row_focus;
    Color button_fill;  // a light tint: the home screen's buttons
    Color tile_fill;    // a fainter one: the recently played tiles
    Color plate_focus;  // under the highlight of buttons, tiles and the header's links
    Color inset;        // tracks and wells sunk into a panel
    Color status_panel; // the home screen's notice panel
    Color cover_top;    // a cover not loaded yet: a dark gradient
    Color cover_bottom;
    Color divider;      // the footer's line
    // ---- colour: controls ----
    Color toggle_track;
    Color toggle_end;   // the far end of a switch that is on
    Color level_track;  // a level bar's empty part
    Color scroll_track;
    Color scroll_thumb;
    Color controller;   // a connected controller's picture
    // ---- colour: high contrast (Settings > Accessibility) ----
    Color hc_panel;
    Color hc_panel_edge;
    Color hc_row;
    Color hc_row_edge;
    Color hc_focus;
    Color hc_focus_edge;
    // ---- colour: the accent (one meaning a screen: where you are) ----
    Color accent;
    Color accent_deep; // the far end of its gradients
    Color accent_pale; // values, kickers, the focus ring
    Color on_accent;   // ink on an accent_pale fill (the folder's arrow)
    Color highlight;   // light in the artwork
    // ---- colour: text, from the brightest to the faintest ----
    Color text;
    Color title;
    Color value;
    Color body;
    Color copy;
    Color meta;
    Color label;
    Color muted;
    Color faint;
    Color warning; // what needs the player (always with a mark, never the colour alone)
    Color rule;    // dividing lines
    Color note;       // a dialog's line under its title
    Color row_name;   // a row's name in a list
    Color folder;     // a folder's icon
    Color kicker;     // the home screen's small capital headings
    Color caption;    // the home screen's version and status line
    Color clock;
    Color detail;     // the lines under the game to continue
    Color nav;        // the header's links at rest
    Color tile_title; // a recently played game's name at rest

    // ---- type: one family, sizes in virtual pixels (the screen is 1920 by 1080) ----
    float size_display = 48.0f; // a screen's title
    float size_lead = 40.0f;
    float size_brand = 36.0f;
    float size_heading = 32.0f;
    float size_clock = 28.0f;
    float size_text = 24.0f;  // rows, actions
    float size_small = 20.0f; // values, hints, captions

    // ---- motion (springs in rad/s, times in seconds) ----
    float focus_spring = 20.0f;
    float cursor_spring = 26.0f;
    float scroll_spring = 16.0f;
    float screen_seconds = 0.30f;
    float launch_seconds = 0.95f;
};

// An accent colour preset: a named set of the accent roles a theme can swap.
struct AccentPreset
{
    const char *id;   // in the settings file (/launcher/accent)
    const char *name; // shown in Settings (a name: not translated)
    Color accent;
    Color accent_deep;
    Color accent_pale;
    Color on_accent;
    Color highlight;
};

// The theme in use. Read where things are drawn, so a change of theme shows in the next frame.
const Theme &th();
// Every theme this build has, the first being the one a new install uses (Eglantine).
std::span<const Theme> themes();
// The place of the one in use in themes().
int theme_index();
// Puts a theme in use by its id (its own accent); false when this build has none of that id
// (the one in use stays).
bool use_theme(std::string_view id);
// The accent presets of the theme in use; the first is the theme's own colours.
std::span<const AccentPreset> accent_presets();
// Which accent preset is in use (0: the theme's own colours).
int accent_index();
// Lays an accent preset of the theme in use over it by id; "", the first preset's id or an id the
// theme has not restores the theme's own colours.
void use_accent(std::string_view id);

// How the launcher is shown: Settings > Accessibility. It lies over whatever theme is in use.
struct Look
{
    bool large_text = false;    // small text is drawn larger
    bool high_contrast = false; // solid panels, brighter text, an outlined highlight
    bool reduce_motion = false; // nothing drifts, slides or zooms: screens fade
};
inline Look &look()
{
    static Look value;
    return value;
}
// 1 normally, 0 with reduced motion: every slide, zoom and drift is multiplied by it.
inline float motion()
{
    return look().reduce_motion ? 0.0f : 1.0f;
}
// The size text of `size` is drawn at. "Larger text" raises everything under 30 to between 26
// and 30 (26 is the least the console accessibility guidelines ask of text on a 1080p TV).
inline float text_size(float size)
{
    return look().large_text && size < 30.0f ? std::clamp(size * 1.3f, 26.0f, 30.0f) : size;
}

// The baseline that centres text of `size` in a line box of height `line` starting at `top`.
inline float baseline(float top, float line, float size)
{
    return top + line * 0.5f + size * 0.35f;
}

inline bool inside(const Rect &r, float x, float y)
{
    return x >= r.x && y >= r.y && x < r.x + r.w && y < r.y + r.h;
}

} // namespace pe::ui
