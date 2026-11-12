pragma Singleton
import QtQuick
import QtCore

// User preferences, persisted with QSettings (organization "i4c", app "Cryo";
// demo mode runs as "Cryo-demo", so it never touches the real file; tests
// and the tour point XDG_CONFIG_HOME at a temp dir). Every key the Settings
// page needs exists here; the page only builds UI on top of them.
// See docs/THEME.md for how style and accent feed Theme.
Settings {
    // Visual style: "cryo" (default), "aurora", "glacier" (light), "blackout".
    property string style: "cryo"
    // Accent override: "" = the style's own accent, else "#RRGGBB".
    property string accent: ""
    // Thermal chrome: frost overlay, flash freeze, heat-driven washes.
    property bool effects: true
    // No looping, sweeping or easing animation (Ambient.motion is false).
    property bool reduceMotion: false
    // UI sounds (off by default), the set and its volume 0..1.
    property bool soundEnabled: false
    property string soundSet: "ice"
    property real soundVolume: 0.6
    // Frost's one-line status in the footer.
    property bool frostLine: true
}
