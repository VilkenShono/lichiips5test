# Launcher themes

The launcher's look is a theme. A theme is data: it gives a colour to every role the screens
use (the accent, a panel, a title, a row at rest, a switch's track...), the sizes of the type and
the speed of the motion. The screens never name a colour of their own; they ask the theme in use
for a role (`th().accent`, `th().panel`), so changing the theme changes the next frame.

## Choosing one

**Settings > Accessibility** starts with two rows:

- **Theme** - Left and Right (or Cross) step through the built-in themes. The detail line under
  the rows says what the highlighted theme looks like.
- **Accent color** - the highlight colors of the theme in use. The first is the theme's own;
  the others swap the accent, its deep and pale ends, the ink drawn on it and the light in the
  artwork. Choosing another theme starts it with its own accent.

The change shows at once and is saved in the settings file
(`config/eglantineps5.json` in the app's data folder, `/data/eglantineps5`):

```json
"launcher": { "theme": "eglantine", "accent": "" }
```

An empty accent is the theme's own. A missing `launcher` section, or a theme id this build does not
have (a file from another version), shows the default theme. Ids are short: lowercase letters,
digits and `-`.

## The built-in themes

| Id          | Name      | Look                                        | Accent colors |
|-------------|-----------|---------------------------------------------|---------------|
| `eglantine` | Eglantine | dark rose glass and petal pink (the default) | Rose, Coral, Amber, Lilac, Ocean, Mint, Silver |
| `canopy`    | Canopy    | tropical dusk, dark green glass and lime    | Lime, Gold, Ember, Teal, Sakura, Ocean, Violet |
| `slate`     | Slate     | neutral glass, clean and still              | Silver, Ice, Rose, Amber, Mint, Lilac, Sky |

Eglantine is the launcher as it always looked: every role is set to the colour the screens used
before themes, so nothing changes for a player who does not choose another. The other themes set
their main roles (surfaces, accent, text) and leave the rest (switch tracks, cover placeholders,
high-contrast panels, the home screen's smaller text) to mixes of those.

All themes share the launcher's artwork (the backdrop, the brand) and its sounds; themes change
colour only, not where anything is. **High contrast** (the next switch down) lies over any theme
with solid panels and an outlined highlight in that theme's colours.

## Adding a theme

1. Write a function in `headless/eglantineps5/pe/ui/theme.cpp` that fills a `Theme` (the roles
   are listed and described in `theme.hpp`): its id, name and one-line summary (marked with
   `TR()` so it can be translated), its main colours, then `derive_roles(t)` for the rest.
2. Add it to the `Store`'s list (after Eglantine, which stays first) and give it a list of accent
   presets in `presets_for`, its own colours first.
3. Run `python3 tools/launcher/strings.py extract` for the new summary, and
   `python3 tools/check-launcher-theme.py`.

`tools/check-launcher-theme.py` (part of the host checks in `tools/build-headless-host.sh`)
fails when a screen writes a colour as a number instead of naming a role (a QR code, dark on
white in every theme, is marked `theme: fixed`), when Eglantine is not the default or differs
from the rose look, and when `theme.cpp`, built and run on the PC, leaves a role of a theme unset
or picks themes and accents other than `theme.hpp` says.

Not included: launcher packs loaded at run time (scripted layouts and artwork from a folder on
the console). Themes are built in.
