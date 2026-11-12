import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import QtQuick.Shapes

// A slab of ice: a vertical gradient from panelTop to panel, a facet line
// catching the light along the top edge, one faint flat facet plane across
// the body, and a soft drop shadow. All of it is static: it repaints only
// when the panel resizes, the style changes, the heat moves (1 Hz at most)
// or the pointer enters or leaves (hover glow, 150 ms).
Rectangle {
    id: panelRect
    radius: 12
    border.width: 1
    border.color: Theme.mix(Theme.panelBorder, Theme.accent, 0.55 * hoverT)
    gradient: Gradient {
        GradientStop { position: 0.0; color: panelRect.iceTop }
        GradientStop { position: 0.55; color: Theme.mix(panelRect.iceTop, Theme.panel, 0.8) }
        GradientStop { position: 1.0; color: Theme.panel }
    }
    // Dark styles lift the top a breath toward the frost tint: the cold
    // light the slab carries. Light styles are already pale at the top.
    readonly property color iceTop: Theme.isLight ? Theme.panelTop
                                                  : Theme.mix(Theme.panelTop, Theme.frost, 0.035)

    // Where the facet plane crosses the top edge, as a fraction of the
    // width (a panel with a busy left side moves it right).
    property real sheenAt: 0.46
    // Hover glow: the border and the shadow lean toward the accent.
    property bool hoverGlow: true
    readonly property bool hovered: panelHover.hovered
    property real hoverT: hoverGlow && panelHover.hovered ? 1 : 0
    Behavior on hoverT {
        enabled: Ambient.motion
        NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
    }
    HoverHandler { id: panelHover }

    // Soft drop shadow. Blurs a hidden, content-free copy of the panel
    // shape, so it re-renders only when the panel resizes. The hover tint
    // is a uniform of the same pass (no extra layer).
    Rectangle {
        id: panelShadowSrc
        anchors.fill: parent
        radius: panelRect.radius
        color: Theme.shadow
        visible: false
    }
    MultiEffect {
        // The effect also draws its source, a panel-shaped fill in the
        // shadow colour, hidden under the opaque panel. While the sections
        // fade in (first-show reveal) the panel is see-through, so the whole
        // effect settles in afterwards (Ambient.revealShadow).
        z: -1
        opacity: Ambient.revealShadow
        visible: opacity > 0
        source: panelShadowSrc
        anchors.fill: panelShadowSrc
        shadowEnabled: true
        shadowColor: Theme.mix(Theme.shadow, Theme.accent, 0.4 * panelRect.hoverT)
        shadowOpacity: Theme.shadowOpacity * (1 + 0.25 * panelRect.hoverT)
        shadowBlur: 1.0
        blurMax: 24
        shadowVerticalOffset: 6
    }

    // The facet plane: one flat, slightly brighter (on light styles slightly
    // shaded) band through the ice, sharp on its leading edge and fading on
    // the trailing one, filled inside the exact rounded outline.
    readonly property color sheenInk: Qt.alpha(Theme.frostInk, Theme.isLight ? 0.045 : 0.028)
    Shape {
        anchors.fill: parent
        anchors.margins: 1
        ShapePath {
            strokeWidth: -1
            strokeColor: "transparent"
            fillGradient: LinearGradient {
                // a fixed 30 degree slant and pixel width, whatever the size
                x1: panelRect.width * panelRect.sheenAt; y1: 0
                x2: x1 + 190; y2: 110
                GradientStop { position: 0.00; color: Qt.alpha(panelRect.sheenInk, 0) }
                GradientStop { position: 0.30; color: Qt.alpha(panelRect.sheenInk, 0) }
                GradientStop { position: 0.31; color: panelRect.sheenInk }
                GradientStop { position: 0.52; color: Qt.alpha(panelRect.sheenInk, panelRect.sheenInk.a * 0.45) }
                GradientStop { position: 0.70; color: Qt.alpha(panelRect.sheenInk, 0) }
                GradientStop { position: 1.00; color: Qt.alpha(panelRect.sheenInk, 0) }
            }
            PathRectangle {
                x: 0; y: 0
                width: panelRect.width - 2
                height: panelRect.height - 2
                radius: panelRect.radius - 1
            }
        }
    }

    // Inner rim: the slab's thickness, a hairline of cold light just inside
    // the border (on a light style a shade instead).
    Rectangle {
        anchors.fill: parent
        anchors.margins: 1
        radius: panelRect.radius - 1
        color: "transparent"
        border.width: 1
        border.color: Qt.alpha(Theme.frostInk, Theme.isLight ? 0.06 : 0.035)
    }

    // Facet highlight: light caught by the top edge, brightest left of
    // centre and gone at both ends, with a softer line under it. It warms
    // a little with the heat.
    readonly property real warmth: Ambient.dormant ? 0 : Ambient.heat
    readonly property color highlightInk: {
        const h = Theme.panelHighlight
        // dark styles: a stronger edge than the token's fill strength
        const a = Theme.isLight ? h.a : Math.min(1, h.a * 3.4)
        return Theme.blend(Qt.alpha(h, a), Qt.alpha(Theme.warn, a), 0.32 * warmth)
    }
    Rectangle {
        x: panelRect.radius * 0.6
        y: 0
        width: parent.width - 2 * x
        height: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.00; color: Qt.alpha(panelRect.highlightInk, 0) }
            GradientStop { position: 0.30; color: panelRect.highlightInk }
            GradientStop { position: 0.55; color: Qt.alpha(panelRect.highlightInk, panelRect.highlightInk.a * 0.7) }
            GradientStop { position: 1.00; color: Qt.alpha(panelRect.highlightInk, 0) }
        }
    }
    Rectangle {
        x: panelRect.radius * 1.4
        y: 1
        width: parent.width - 2 * x
        height: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.00; color: Qt.alpha(panelRect.highlightInk, 0) }
            GradientStop { position: 0.28; color: Qt.alpha(panelRect.highlightInk, panelRect.highlightInk.a * 0.35) }
            GradientStop { position: 0.50; color: Qt.alpha(panelRect.highlightInk, panelRect.highlightInk.a * 0.15) }
            GradientStop { position: 1.00; color: Qt.alpha(panelRect.highlightInk, 0) }
        }
    }
}
