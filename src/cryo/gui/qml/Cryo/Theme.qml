pragma Singleton
import QtQuick

// Look tokens: the one place colours, faces and presentation maps live.
// Components read these by name (Theme.accent, Theme.tempColor(t) ...);
// no other QML file holds a colour literal (tests/test_gui_tokens.py).
// The contract, every token and how to add a style: docs/THEME.md.
QtObject {
    id: theme

    // ---- styles: one object per style, every object has the same keys ----
    // Colours are "#RRGGBB" or "#AARRGGBB" (alpha first, Qt's order).
    readonly property var styles: ({
        "cryo": {
            isLight: false,
            bg: "#000102",
            washColdA: "#2E3D5BFF", washColdB: "#1400D1FF",
            washHotA: "#2EFF2D6A", washHotB: "#14FF8A00",
            washNeutral: "#0C828690",
            panel: "#090D14", panelTop: "#0D131D",
            panelBorder: "#1A2233", panelHighlight: "#14FFFFFF",
            track: "#141A26",
            fg: "#F3F5F9", muted: "#828690",
            accent: "#00D1FF", accent2: "#7B2DFF", accent2Text: "#A082FF",
            knob: "#F3F5F9",
            frost: "#BFEFFF", frostRim: "#FFFFFF", frostShade: "#4A6478", frostInk: "#D6F5FF",
            frostShadeStrength: 0, frostIntensity: 0.72,
            hot: "#FF5470", warn: "#FFB300", ok: "#3DDC97",
            shadow: "#000000", shadowOpacity: 0.9, glow: 1.0,
            deck: "#06080D", deckEdge: "#1A2233", keycap: "#0B0F17", keycapEdge: "#0DF3F5F9",
            ledOff: "#000000"
        },
        "aurora": {
            isLight: false,
            bg: "#020A0C",
            washColdA: "#263DF5B4", washColdB: "#168A5CFF",
            washHotA: "#2AFF4F6E", washHotB: "#14FFB040",
            washNeutral: "#0C7F9A97",
            panel: "#071417", panelTop: "#0A1C20",
            panelBorder: "#153038", panelHighlight: "#14E0FFF4",
            track: "#10262C",
            fg: "#EFFAF6", muted: "#7F9A97",
            accent: "#3DF5B4", accent2: "#8A5CFF", accent2Text: "#B49CFF",
            knob: "#EFFAF6",
            frost: "#C8FFF0", frostRim: "#F2FFFA", frostShade: "#3F6A66", frostInk: "#D2FFF2",
            frostShadeStrength: 0, frostIntensity: 0.85,
            hot: "#FF5470", warn: "#FFB300", ok: "#3DDC97",
            shadow: "#000000", shadowOpacity: 0.9, glow: 0.9,
            deck: "#050C0E", deckEdge: "#153038", keycap: "#0A1416", keycapEdge: "#0DEFFAF6",
            ledOff: "#000000"
        },
        "glacier": {
            isLight: true,
            bg: "#E9F2F8",
            washColdA: "#4D8CC8EE", washColdB: "#2E00A3D6",
            washHotA: "#3DFF9A86", washHotB: "#2EFFC46A",
            washNeutral: "#145B7386",
            panel: "#F9FCFE", panelTop: "#FFFFFF",
            panelBorder: "#C9DCE8", panelHighlight: "#FFFFFFFF",
            track: "#D7E5EE",
            fg: "#0B2233", muted: "#566E80",
            accent: "#006B93", accent2: "#6A3DE8", accent2Text: "#5A32C8",
            knob: "#FFFFFF",
            frost: "#FFFFFF", frostRim: "#FFFFFF", frostShade: "#5F87A3", frostInk: "#3A7CA5",
            frostShadeStrength: 0.7, frostIntensity: 0.95,
            hot: "#C21E3C", warn: "#9E5C00", ok: "#17845A",
            shadow: "#5A7A95", shadowOpacity: 0.22, glow: 0.45,
            deck: "#0B1119", deckEdge: "#22303F", keycap: "#111824", keycapEdge: "#14F3F5F9",
            ledOff: "#000000"
        },
        "blackout": {
            isLight: false,
            bg: "#000000",
            washColdA: "#0C9BE7FF", washColdB: "#06FFFFFF",
            washHotA: "#0EFF5470", washHotB: "#06FFB300",
            washNeutral: "#067A7A7A",
            panel: "#050505", panelTop: "#080808",
            panelBorder: "#1C1C1C", panelHighlight: "#0DFFFFFF",
            track: "#151515",
            fg: "#EDEDED", muted: "#7A7A7A",
            accent: "#9BE7FF", accent2: "#6E6E78", accent2Text: "#A0A0AA",
            knob: "#EDEDED",
            frost: "#DDEFF5", frostRim: "#F4FBFD", frostShade: "#3A4A52", frostInk: "#E4F4FA",
            frostShadeStrength: 0, frostIntensity: 0.6,
            hot: "#FF5470", warn: "#FFB300", ok: "#3DDC97",
            shadow: "#000000", shadowOpacity: 0.9, glow: 0.35,
            deck: "#030303", deckEdge: "#1C1C1C", keycap: "#0A0A0A", keycapEdge: "#0DEDEDED",
            ledOff: "#000000"
        }
    })
    readonly property var styleNames: ["cryo", "aurora", "glacier", "blackout"]
    readonly property var styleLabels: ({
        "cryo": "Cryo", "aurora": "Aurora", "glacier": "Glacier", "blackout": "Blackout"
    })
    // One line per style for the Settings style picker.
    readonly property var styleBlurbs: ({
        "cryo": "Deep black, cyan and violet.",
        "aurora": "Polar night, green light.",
        "glacier": "Light. Pale ice and navy.",
        "blackout": "Pure black, minimal glow."
    })
    // Accent override choices (Settings). Data, not theme: Prefs.accent
    // stores the raw colour and Theme derives what is drawn (readableOn).
    readonly property var accentChoices: [
        { name: "Cyan", color: "#00D1FF" },
        { name: "Ice", color: "#9BE7FF" },
        { name: "Aurora", color: "#3DF5B4" },
        { name: "Violet", color: "#8A5CFF" },
        { name: "Magenta", color: "#FF4FD8" },
        { name: "Amber", color: "#FFB300" },
        { name: "Ember", color: "#FF6B4A" },
        { name: "Rose", color: "#FF5470" }
    ]
    // A style name is valid only if it is in styleNames (own keys of
    // `styles`): `styles[name] !== undefined` would accept "toString",
    // "constructor" or "__proto__" from a hand-edited settings file.
    function resolveStyle(name) {
        return styleNames.indexOf(name) >= 0 ? name : "cryo"
    }
    function styleFor(name) {
        return styles[resolveStyle(name)]
    }
    readonly property string styleName: resolveStyle(Prefs.style)
    readonly property var s: styles[styleName]
    // Changes whenever anything a Canvas painted could change; canvases
    // repaint on it (they do not re-run bindings by themselves).
    readonly property string revision: styleName + "|" + accent

    // ---- tokens: each reads the active style ----
    readonly property bool isLight: s.isLight
    readonly property color bg: s.bg
    readonly property color washColdA: s.washColdA     // large wash, top left
    readonly property color washColdB: s.washColdB     // small wash, right
    readonly property color washHotA: s.washHotA
    readonly property color washHotB: s.washHotB
    readonly property color washNeutral: s.washNeutral // daemon unreachable
    readonly property color panel: s.panel
    readonly property color panelTop: s.panelTop
    readonly property color panelBorder: s.panelBorder
    readonly property color panelHighlight: s.panelHighlight
    readonly property color track: s.track
    readonly property color fg: s.fg
    readonly property color muted: s.muted
    // The accent override replaces this one token and nothing else.
    // An override is drawn as readableOn(override, panel): unchanged when it
    // already reads as text on the style's panel, else moved toward black
    // (light styles) or white (dark ones) until it does. See docs/THEME.md.
    readonly property bool accentOverridden: /^#[0-9A-Fa-f]{6}$/.test(Prefs.accent)
    readonly property color accent: accentFor(styleName)
    readonly property color styleAccent: s.accent
    readonly property color accent2: s.accent2
    readonly property color accent2Text: s.accent2Text
    readonly property color knob: s.knob
    readonly property color frost: s.frost
    readonly property color frostRim: s.frostRim
    readonly property color frostShade: s.frostShade
    // Frost drawn as a mark on the window (bloom crystals, guard motes, the
    // reveal glint, the ice sheen in panels): stays visible on this style's
    // panel and background (pale on dark styles, deeper ice blue on light).
    readonly property color frostInk: s.frostInk
    readonly property real frostShadeStrength: s.frostShadeStrength
    readonly property real frostIntensity: s.frostIntensity
    readonly property color hot: s.hot
    readonly property color warn: s.warn
    readonly property color ok: s.ok
    readonly property color shadow: s.shadow
    readonly property real shadowOpacity: s.shadowOpacity
    readonly property real glow: s.glow                // neon bloom multiplier
    readonly property color deck: s.deck               // keyboard preview deck
    readonly property color deckEdge: s.deckEdge
    readonly property color keycap: s.keycap           // keyboard preview caps
    readonly property color keycapEdge: s.keycapEdge
    readonly property color ledOff: s.ledOff           // an unlit keyboard zone

    // Real LED colours (the keyboard's "quantum" effect and the default
    // lighting colour): fixed, they never follow the style or the accent.
    readonly property color ledCyan: "#00D1FF"
    readonly property color ledViolet: "#7B2DFF"

    // ---- type ----
    // Controls (and every Label) inherit the window font; Outfit is the UI
    // face, JetBrains Mono / tabular figures keep live numbers from jittering.
    readonly property string uiFont: outfitRegular.font.family
    readonly property string monoFont: monoRegular.font.family
    readonly property FontLoader outfitRegular: FontLoader { source: "../../assets/fonts/Outfit-Regular.ttf" }
    readonly property FontLoader monoRegular: FontLoader { source: "../../assets/fonts/JetBrainsMono-Regular.ttf" }
    // The other Outfit weights only need to be registered with the font
    // database; font.weight picks them by family.
    readonly property list<QtObject> outfitWeights: [
        FontLoader { source: "../../assets/fonts/Outfit-Medium.ttf" },
        FontLoader { source: "../../assets/fonts/Outfit-SemiBold.ttf" },
        FontLoader { source: "../../assets/fonts/Outfit-Bold.ttf" }
    ]

    // ---- power-mode presentation (grid renders daemon.profiles) ----
    // Icon names under src/cryo/gui/assets/icons (drawn through Icon.qml).
    readonly property var profileIcons: ({
        "cool": "mode-cool", "quiet": "mode-quiet", "balanced": "mode-balanced",
        "performance": "mode-performance", "gmode": "mode-gmode", "custom": "mode-custom",
        "low-power": "mode-low-power"
    })
    readonly property var profileLabels: ({
        "cool": "Cool", "quiet": "Quiet", "balanced": "Balanced",
        "performance": "Performance", "gmode": "G-Mode", "custom": "Custom",
        "low-power": "Low Power"
    })
    // One-row grid labels: up to 7 modes share 400 px at the minimum width.
    readonly property var profileShortLabels: ({
        "performance": "Perf", "low-power": "Low Pwr"
    })

    // ---- helpers ----
    // Opaque mix of two colours (alpha 1).
    function mix(a, b, f) {
        return Qt.rgba(a.r + (b.r - a.r) * f, a.g + (b.g - a.g) * f, a.b + (b.b - a.b) * f, 1)
    }
    // Mix including alpha (washes and other translucent tokens).
    function blend(a, b, f) {
        return Qt.rgba(a.r + (b.r - a.r) * f, a.g + (b.g - a.g) * f,
                       a.b + (b.b - a.b) * f, a.a + (b.a - a.a) * f)
    }
    // WCAG 2 relative luminance and contrast ratio.
    function _linear(v) {
        return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
    }
    function luminance(c) {
        const k = Qt.color(c)
        return 0.2126 * _linear(k.r) + 0.7152 * _linear(k.g) + 0.0722 * _linear(k.b)
    }
    function contrast(a, b) {
        const la = luminance(a), lb = luminance(b)
        return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
    }
    // `c` as text on `background` (at least 4.5:1): unchanged when it
    // already reads, else the same hue and saturation at the HSL lightness
    // nearest the original that does (darker on a light background, lighter
    // on a dark one). Lightness moves every channel the same way, so
    // contrast is monotonic in it and a bisection finds the edge. Pure.
    readonly property real textContrast: 4.5
    function readableOn(c, background) {
        const k = Qt.color(c)
        const target = theme.textContrast + 0.05      // margin for 8-bit rounding
        if (contrast(k, background) >= target)
            return k
        const darken = luminance(background) > 0.18
        const h = Math.max(0, k.hslHue), sat = k.hslSaturation
        let ok = darken ? 0 : 1                       // always readable
        let bad = k.hslLightness
        for (let i = 0; i < 24; i++) {
            const mid = (ok + bad) / 2
            if (contrast(Qt.hsla(h, sat, mid, 1), background) >= target)
                ok = mid
            else
                bad = mid
        }
        return Qt.hsla(h, sat, ok, 1)
    }
    // The accent a style draws with, given the current override.
    function accentFor(name) {
        const st = styleFor(name)
        return accentOverridden ? readableOn(Prefs.accent, st.panel) : Qt.color(st.accent)
    }
    // Gauge colour by temperature: accent while cool, accent2 under load,
    // amber as it warms, red from 85 °C (where the number turns red too).
    function tempColor(t) {
        const stops = [[45, theme.accent], [65, theme.accent2], [78, theme.warn], [85, theme.hot]]
        if (t <= stops[0][0])
            return stops[0][1]
        for (let i = 1; i < stops.length; i++) {
            if (t <= stops[i][0]) {
                const a = stops[i - 1], b = stops[i]
                return theme.mix(a[1], b[1], (t - a[0]) / (b[0] - a[0]))
            }
        }
        return theme.hot
    }
}
