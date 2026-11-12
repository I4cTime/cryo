import QtQuick
import QtQuick.Shapes

// Ambient backdrop: two faint washes behind the content whose colours follow
// the machine's heat (the style's cold colours at Ambient.heat 0, its hot
// colours at 1). While Thermal Guard holds, the washes run cold (emergency
// cooling); with no temperatures (dormant) they fade to a faint neutral.
// A small per-profile tint: Cool leans icier, Performance and G-Mode lean
// toward accent2. With Prefs.effects off it is the style's static cold look.
//
// Cost: heat moves in whole-degree steps at 1 Hz, so the gradients change at
// most once a second and are never tessellated again (only resizes do that).
// The only easing is on discrete state changes (guard, dormant, profile).
Shape {
    id: backdrop
    anchors.fill: parent

    readonly property bool fx: Prefs.effects
    // 0..1 state mixes, eased on change (one-shot, gated on motion).
    property real guardMix: fx && Ambient.guard ? 1 : 0
    property real dormantMix: fx && Ambient.dormant ? 1 : 0
    property real icyMix: fx && Ambient.profile === "cool" ? 1 : 0
    property real loadMix: fx && (Ambient.profile === "performance" || Ambient.profile === "gmode") ? 1 : 0
    Behavior on guardMix { enabled: Ambient.motion; NumberAnimation { duration: 900; easing.type: Easing.InOutSine } }
    Behavior on dormantMix { enabled: Ambient.motion; NumberAnimation { duration: 1200; easing.type: Easing.InOutSine } }
    Behavior on icyMix { enabled: Ambient.motion; NumberAnimation { duration: 900 } }
    Behavior on loadMix { enabled: Ambient.motion; NumberAnimation { duration: 900 } }

    readonly property real heat: fx ? Ambient.heat : 0
    readonly property real profileTint: 0.22   // how far the profile leans the hue

    function wash(cold, hot) {
        let c = Theme.blend(cold, hot, backdrop.heat)
        // profile lean: hue only, the wash keeps its strength
        c = Theme.blend(c, Qt.alpha(Theme.frost, c.a), backdrop.icyMix * backdrop.profileTint)
        c = Theme.blend(c, Qt.alpha(Theme.accent2, c.a), backdrop.loadMix * backdrop.profileTint)
        // guard: back to the cold colour, a little stronger
        c = Theme.blend(c, Qt.alpha(cold, Math.min(1, cold.a * 1.35)), backdrop.guardMix)
        return Theme.blend(c, Theme.washNeutral, backdrop.dormantMix)
    }
    readonly property color washA: wash(Theme.washColdA, Theme.washHotA)
    readonly property color washB: wash(Theme.washColdB, Theme.washHotB)

    ShapePath {
        strokeColor: "transparent"
        fillGradient: RadialGradient {
            centerX: backdrop.width * 0.12; centerY: -40
            centerRadius: backdrop.width * 0.95
            focalX: centerX; focalY: centerY
            GradientStop { position: 0.0; color: backdrop.washA }
            GradientStop { position: 1.0; color: Qt.alpha(backdrop.washA, 0) }
        }
        startX: 0; startY: 0
        PathLine { x: backdrop.width; y: 0 }
        PathLine { x: backdrop.width; y: backdrop.height }
        PathLine { x: 0; y: backdrop.height }
        PathLine { x: 0; y: 0 }
    }
    ShapePath {
        strokeColor: "transparent"
        fillGradient: RadialGradient {
            centerX: backdrop.width * 0.95; centerY: backdrop.height * 0.35
            centerRadius: backdrop.width * 0.8
            focalX: centerX; focalY: centerY
            GradientStop { position: 0.0; color: backdrop.washB }
            GradientStop { position: 1.0; color: Qt.alpha(backdrop.washB, 0) }
        }
        startX: 0; startY: 0
        PathLine { x: backdrop.width; y: 0 }
        PathLine { x: backdrop.width; y: backdrop.height }
        PathLine { x: 0; y: backdrop.height }
        PathLine { x: 0; y: 0 }
    }
}
