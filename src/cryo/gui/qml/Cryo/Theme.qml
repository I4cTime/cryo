pragma Singleton
import QtQuick

// Look tokens: the one place colours, faces and presentation maps live.
// Components read these by name (Theme.accent, Theme.tempColor(t) ...);
// no other file holds a palette colour literal.
QtObject {
    id: theme

    // ---- quantum fluidity tokens (lib/palette.ts equivalents) ----
    readonly property color bg: "#000102"
    readonly property color accent: "#00D1FF"
    readonly property color accent2: "#7B2DFF"
    readonly property color accent2Text: "#A082FF"
    readonly property color frost: "#BFEFFF"
    readonly property color fg: "#F3F5F9"
    readonly property color muted: "#828690"
    readonly property color panel: "#090D14"
    readonly property color panelBorder: "#1A2233"
    readonly property color track: "#141A26"
    readonly property color hot: "#FF5470"
    readonly property color warn: "#FFB300"
    readonly property color ok: "#3DDC97"
    readonly property color shadow: "#000000"
    readonly property color deck: "#06080D"       // keyboard preview deck
    readonly property color keycap: "#0B0F17"     // keyboard preview caps
    readonly property color ledOff: "#000000"     // an unlit keyboard zone

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
    readonly property var profileGlyphs: ({
        "cool": "❄", "quiet": "🌙", "balanced": "⚖", "performance": "🚀",
        "gmode": "👾", "custom": "🎛", "low-power": "🍃"
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
    function mix(a, b, f) {
        return Qt.rgba(a.r + (b.r - a.r) * f, a.g + (b.g - a.g) * f, a.b + (b.b - a.b) * f, 1)
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
