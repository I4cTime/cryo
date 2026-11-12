# Cryo GUI theme contract

The Cryo window is drawn from tokens. Every colour, alpha and glow strength a
component paints with comes from the `Theme` singleton
(`src/cryo/gui/qml/Cryo/Theme.qml`); components never hold colour literals.
This is what lets a style switch or an accent override re-theme the whole
window live.

## The pieces

| Singleton | File | Role |
|---|---|---|
| `Prefs` | `Cryo/Prefs.qml` | User choices, persisted with QtCore `Settings` (QSettings: organization `i4c`, application `Cryo`; demo mode is `Cryo-demo`). Keys: `style`, `accent`, `effects`, `reduceMotion`, `soundEnabled`, `soundSet`, `soundVolume`, `frostLine`. |
| `Theme` | `Cryo/Theme.qml` | The styles (data) and the tokens (properties reading the active style), fonts, the power-mode maps and helpers. |
| `Ambient` | `Cryo/Ambient.qml` | Runtime state: `live`, `motion`, `connected`, `stale`, `heat`, `dormant`, `guard`, `guardPhase`, `frostAmount`, `edgeIce`. |

## Styles

`Prefs.style` picks one of four styles; an unknown name falls back to `cryo`.

| Style | Look |
|---|---|
| `cryo` (default) | Near-black blue, cyan accent, violet secondary, full neon glow. |
| `aurora` | Teal-black, aurora green accent, violet secondary. |
| `glacier` | Light: pale ice background, near-white panels, dark navy text, a deeper cyan accent for contrast, soft blue-grey shadows, frost drawn as blue-grey crystals. |
| `blackout` | Pure black, pale ice accent, grey secondary, minimal glow, washes nearly off, faint frost. |

Each style is one object in `Theme.styles` and every object has exactly the
same keys. Colours are `"#RRGGBB"` or `"#AARRGGBB"` (alpha first, Qt's order).

## Tokens

Every key below is a `Theme` property of the same name that reads the active
style.

| Token | Use |
|---|---|
| `isLight` | True for light styles (glacier). Use it only where a light background needs a different treatment, never to pick colours. |
| `bg` | Window background. |
| `washColdA`, `washColdB` | The two backdrop washes (A large, top left; B small, right) when the machine is cold. Translucent. |
| `washHotA`, `washHotB` | The same washes when it is hot. `Backdrop.qml` blends cold to hot by `Ambient.heat`. |
| `washNeutral` | Both washes when dormant (daemon unreachable, no thermals). |
| `panel` | Panel, card and button fill. |
| `panelTop` | The lighter top of a panel gradient (for the ice material). |
| `panelBorder` | Panel, control and divider lines. |
| `panelHighlight` | The facet line along a panel's top edge. |
| `panelOpacity` | Opacity of the panel fill alone (`Panel.qml`), 0..1. At 1 the slab is solid; below 1 the frost and the backdrop ghost faintly through it, like looking through a slab of ice. The text, controls, border, facet lines and drop shadow are never affected (the shadow masks itself out of the panel's shape when the fill is see-through). Panel text must keep AA over the worst case, the fill blended over pure frost at `frostIntensity` (see Contrast). All four styles ship at 1. |
| `track` | Slider and gauge tracks, neutral button fill, spin box fill. |
| `fg` | Primary text and values. |
| `muted` | Secondary text, section titles, inactive icons. |
| `accent` | The highlight colour: active mode, switches, sliders, accent buttons, cool gauge colour. **The only token the accent override changes.** |
| `styleAccent` | The style's own accent, whatever the override says (for a "style default" swatch). |
| `accent2` | Secondary colour: load gauge colour, GPU load bar, gaming badge glow. |
| `accent2Text` | `accent2` tuned for text and thin lines on `panel`. |
| `knob` | Slider handle fill. |
| `frost`, `frostRim` | Frost overlay ice tint and the bright rim at the freeze front. |
| `frostInk` | Frost drawn as a mark on the window: the frost bloom crystal, the guard's ice motes on the brand mark, the reveal glint on section titles, the ice sheen and inner rim of panels. Stays visible on the style's `panel` and `bg` (3:1 or more): pale on dark styles, a deeper ice blue on glacier. |
| `frostShade`, `frostShadeStrength` | Darkening under and inside the ice, for pale styles (0 on dark styles). |
| `frostIntensity` | Maximum frost alpha. |
| `hot`, `warn`, `ok` | Status: too hot / error, warning, healthy. |
| `shadow`, `shadowOpacity` | Panel drop shadow colour and strength. |
| `glow` | Multiplier on every neon bloom (mode halo, badge pulse, gauge bloom, brand mark). |
| `deck`, `deckEdge`, `keycap`, `keycapEdge` | The keyboard preview. A keyboard is black, so these stay dark in every style, light ones included. |
| `ledOff` | An unlit keyboard zone. |

Fixed tokens (outside the styles, never themed):

| Token | Use |
|---|---|
| `ledCyan`, `ledViolet` | Real LED colours: the keyboard's quantum effect and the default lighting colour. They never follow the style or the accent. |

Derived and other members: `styleName` (the active style), `styleNames`,
`styleLabels`, `styleBlurbs` (one line per style for the Settings picker),
`accentChoices`, `accentOverridden`, `revision` (changes on any style or accent
change; a `Canvas` repaints on `onRevisionChanged`, because canvases do not
re-run bindings), `uiFont`, `monoFont`, `profileIcons`, `profileLabels`,
`profileShortLabels`, and the helpers `mix(a, b, f)` (opaque),
`blend(a, b, f)` (with alpha), `tempColor(t)`, and the accent helpers
`readableOn(c, background)`, `accentFor(style)`, `contrast(a, b)`,
`luminance(c)` (see below).

## The accent override

`Prefs.accent` is `""` (use the style's accent) or `"#RRGGBB"`. Anything that
is not a valid colour is ignored and the style's accent applies. Nothing else
changes with the override: secondary colours, status colours, frost and the
LED tokens stay as the style defines them.

The Settings page offers the choices in `Theme.accentChoices` (data, one
`{ name, color }` per swatch) plus "Style default":

| Name | Colour |
|---|---|
| Cyan | `#00D1FF` |
| Ice | `#9BE7FF` |
| Aurora | `#3DF5B4` |
| Violet | `#8A5CFF` |
| Magenta | `#FF4FD8` |
| Amber | `#FFB300` |
| Ember | `#FF6B4A` |
| Rose | `#FF5470` |

`Prefs.accent` always stores the colour as picked. What `Theme.accent` draws
with is derived per style by `Theme.readableOn(colour, panel)`, a pure
function:

1. If the colour already has at least 4.5:1 contrast (WCAG 2, text grade)
   on the style's `panel`, it is used unchanged. Every choice passes on the
   dark styles, so there the override is exact.
2. Otherwise hue and saturation are kept and only the HSL lightness moves:
   toward black when the panel is light (luminance above 0.18), toward white
   when it is dark. Lightness moves every channel the same way, so contrast
   is monotonic in it; a 24-step bisection finds the lightness nearest the
   original that reaches 4.5:1 (aiming at 4.55 to survive 8-bit rounding).

So on Glacier a pale pick such as Ice or Aurora is drawn as a deeper shade of
the same hue, and switching back to a dark style gives the original colour
back. The Settings swatches show the derived colour, and a line under them
says when the active style deepened (or lightened) the pick.
`Theme.accentFor(style)` gives the accent a style would draw with under the
current override (the style cards' previews use it), and
`Theme.contrast(a, b)` / `Theme.luminance(c)` are the WCAG helpers.

`tests/test_gui_settings.py` checks, through the engine, that for every
style and every choice (and the style default) the drawn accent has at least
4.5:1 on that style's `panel` and 3:1 on its `bg`.

Contrast: in every style `fg`, `muted`, `accent`, `accent2Text`, `hot` and
`warn` reach WCAG AA (4.5:1) as text on the panel fill: on `panel`, on
`panelTop` and on the iced top dark styles draw, each at the style's
`panelOpacity` over the window background and over pure frost (`frost`,
`frostRim`, `frostShade` at `frostIntensity`).
`tests/test_gui_tokens.py` computes this from the tokens, so it guards
whatever `panelOpacity` a style picks. Under that worst case the dark styles
stay AA only down to about 0.97 (cryo), 0.94 (aurora) and 0.98 (blackout);
glacier to about 0.88.

## Thermal chrome

- `Ambient.heat` is `max(cpuTemp, gpuTemp)` rounded to a whole degree and
  mapped 45 C -> 0, 85 C -> 1. It changes at most once per telemetry frame
  (1 Hz) and only eases (400 ms) on a jump over 0.15, so it never repaints
  continuously. Dormant (no daemon or no thermals): neutral heat 0.4.
- The window frost (`FrostOverlay` in `Main.qml`) is a background layer:
  drawn above the backdrop washes and below both pages, so every label,
  icon, control and panel of the home column and of Settings sits on top of
  it in every state. It shows behind the header, the section titles and in
  the margins and gaps between panels, strongest in the corners; an opaque
  panel hides it (see `panelOpacity`).
- Labels with no panel behind them (the section titles, the two header
  subtitles, the dGPU row, Frost's footer line) each carry a `Clearing`
  (`Cryo/Clearing.qml`): a soft halo in the ground colour under the label,
  `Backdrop.colourAt` (`bg` with the washes over it at that spot), drawn
  above the frost and below the label, so the ice looks melted back around
  the lettering and nothing shows where there is no ice. It is a Canvas
  (software renderer safe) painted only on resize or a ground change; its
  opacity follows `Ambient.frostAmount`, whole from 0.36 up, 0 with effects
  off. A sibling it reaches under that must stay on top takes `z: 1`. The
  header gear and the Settings close button are `IconButton { backed: true }`:
  round keycaps in `panel` with a `panelBorder` rim.
- `Ambient.frostAmount` drives it: idle frost is
  `idleMax * clamp(1 - heat / 0.6, 0, 1)` with `idleMax` 0.48; Thermal Guard
  sweeps to `peakAmount` 1.0 in 550 ms (`guardPhase` "sweep", the whole
  background freezes over), settles to `heldAmount` 0.60 ("held"), and
  thaws back over 2.5 s on release ("thaw"). Dormant (daemon unreachable or
  no thermals) it eases to a fixed `dormantFrost` 0.42. With `Prefs.effects`
  off it is 0. Under reduce motion
  (or with the window unfocused) there is no sweep: the amount jumps and the
  overlay crossfades for 280 ms.
- The overlay is a little larger than the window, so the ferns that freeze
  first start just outside the pane: 28 px past the sides (`frostBleed`),
  32 px past the top (`frostBleedTop`) and 40 px past the bottom
  (`frostBleedBottom`). The amounts are tied to this placement: changing
  the overflow changes how much of each amount shows.
- Panels take part in the flash freeze without covering anything:
  `Ambient.edgeIce` (0..1) rises with the sweep, holds at 1 while the guard
  holds and falls with the thaw (from wherever it stood, so a release
  mid-sweep or a re-engage mid-thaw never steps). `Panel.qml` leans its
  border (halfway) and its facet highlight toward `frostInk` by it, so the
  slabs look iced at their edges. It is derived from the guard animations,
  so it eases only with motion and jumps otherwise; 0 with effects off.
- Stale telemetry: when cryod is unreachable (`Ambient.stale`) the figures
  on screen are the last reading. The temperature tiles, the dGPU load row
  and the VRAM panel dim to `Ambient.staleOpacity` (0.45), their arcs, lines
  and numbers turn `muted`, and the fan glyphs stop. They stay on screen;
  controls are unchanged.
- `Backdrop.qml` blends the washes by heat, runs them cold while the guard
  holds, fades them to `washNeutral` when dormant, and leans them icier on
  the Cool profile and toward `accent2` on Performance and G-Mode.

## The rule: no colour literals outside Theme

No QML file may contain a `#hex` colour, a named colour string (`"white"`,
`"red"` ...) or a literal `Qt.rgba(...)` except:

- `Cryo/Theme.qml` (the token blocks),
- the `swatches:` line in `Cryo/Lighting.qml` (LED colours are data),
- the `property color` defaults in `Cryo/fx/FrostOverlay.qml` (`Main.qml`
  binds Theme over them).

`"transparent"` is allowed (it is no colour). Comments are ignored. Emoji are
not allowed either: icons come from `src/cryo/gui/assets/icons` through
`Icon.qml` (the `cryoicon` image provider in `cryo/gui/icons.py`).

`tests/test_gui_tokens.py` enforces all of this, checks that every style has
the same keys, and switches through every style and the accent override
through a real QML engine, failing on any QML warning.

## Adding a style

1. Copy a style object in `Theme.styles` (start from `glacier` for a light
   style), give it a new key and change the values. Keep every key.
2. Add the key to `styleNames` and a label to `styleLabels`.
3. Check text contrast on `panel` and `bg` (WCAG AA, 4.5:1) for `fg`,
   `muted`, `accent`, `accent2Text`, `hot` and `warn`.
4. Run `uv run pytest -q tests/test_gui_tokens.py` and the tour:
   `uv run tools/tour.py OUTDIR --style NAME`, then look at every shot,
   especially `idle-cold`, `guard-held`, `disconnected` and `sec-lighting`.

## Adding a token

Add the key to every style object, add a `readonly property` of the same name
to Theme that reads `s.<key>`, document it in the table above, and use it in
components. The key-set test fails if one style misses it.
