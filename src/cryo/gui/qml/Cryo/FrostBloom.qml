import QtQuick
import QtQuick.Shapes
import QtQuick.Effects

// A frost bloom: a six-fold ice crystal (spokes with side branches around a
// small hexagonal plate) that grows from a point and fades, about 450 ms.
// The crystal is one static Shape drawn once; the burst only scales, turns
// and fades it. Fill the parent with it and call burst(x, y).
//
// Clipped to the parent's rounded outline through a mask that exists only
// while a burst plays (on the software renderer, where masks do not draw,
// it falls back to a rectangular clip). Nothing happens without motion.
Item {
    id: bloom
    property real radius: 12
    property color tint: Theme.frostInk
    // how far the spokes reach at full size
    property real reach: Math.max(width, height) * 0.72
    readonly property bool active: burstAnim.running
    readonly property bool masked: GraphicsInfo.api !== GraphicsInfo.Software
                                   && GraphicsInfo.api !== GraphicsInfo.Unknown
    visible: active

    function burst(px, py) {
        if (!Ambient.motion || width <= 0)
            return
        crystal.x = px - crystal.width / 2
        crystal.y = py - crystal.height / 2
        burstAnim.restart()
    }

    Rectangle {
        id: outline
        anchors.fill: parent
        radius: bloom.radius
        visible: false
        layer.enabled: bloom.active && bloom.masked
    }

    Item {
        id: field
        anchors.fill: parent
        clip: !bloom.masked
        layer.enabled: bloom.active && bloom.masked
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: outline
            maskThresholdMin: 0.5
            maskSpreadAtMin: 0.5
        }

        Item {
            id: crystal
            objectName: "bloomCrystal"
            width: 2 * bloom.reach
            height: width
            opacity: 0
            scale: 0.2

            Rectangle {
                // the cold flash at the heart
                anchors.centerIn: parent
                width: bloom.reach * 0.5
                height: width
                radius: width / 2
                color: Qt.alpha(bloom.tint, 0.05)
            }
            Shape {
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    // the plate
                    strokeColor: Qt.alpha(bloom.tint, 0.9)
                    strokeWidth: 1.2
                    fillColor: Qt.alpha(bloom.tint, 0.25)
                    joinStyle: ShapePath.RoundJoin
                    PathSvg { path: bloom.platePath(crystal.width / 2) }
                }
                ShapePath {
                    // the inner half of the spokes and branches, brighter
                    strokeColor: Qt.alpha(bloom.tint, 0.75)
                    strokeWidth: 1.1
                    fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    joinStyle: ShapePath.RoundJoin
                    PathSvg { path: bloom.spokePath(crystal.width / 2, 0.1, 0.5) }
                }
                ShapePath {
                    // the outer half, fainter and finer: the growth front
                    strokeColor: Qt.alpha(bloom.tint, 0.38)
                    strokeWidth: 0.9
                    fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    joinStyle: ShapePath.RoundJoin
                    PathSvg { path: bloom.spokePath(crystal.width / 2, 0.5, 1.0) }
                }
            }
        }
    }

    // The crystal around (c, c): a small hexagonal plate, and six spokes
    // each with three pairs of branches at 60 degrees.
    function _pt(c, r, a) {
        return (c + r * Math.cos(a)).toFixed(2) + " " + (c + r * Math.sin(a)).toFixed(2)
    }
    function platePath(c) {
        const R = c * 0.96
        let d = ""
        for (let i = 0; i < 6; i++)
            d += (i === 0 ? "M " : "L ") + _pt(c, R * 0.1, i * Math.PI / 3 + Math.PI / 6) + " "
        return d + "Z"
    }
    // The spokes between radii `inner` and `outer` (fractions of the reach)
    // and the branch pairs rooted there.
    function spokePath(c, inner, outer) {
        const R = c * 0.96
        const pt = (r, a) => _pt(c, r, a)
        let d = ""
        for (let i = 0; i < 6; i++) {
            const a = i * Math.PI / 3
            d += "M " + pt(R * inner, a) + " L " + pt(R * outer, a) + " "
            // each branch pair as one V (tip, spoke, tip): the curve
            // renderer drops subpaths that start at the same point
            for (const [at, len] of [[0.3, 0.2], [0.56, 0.16], [0.8, 0.09]]) {
                if (at < inner || at >= outer)
                    continue
                const bx = c + R * at * Math.cos(a), by = c + R * at * Math.sin(a)
                const tip = (side) => (bx + R * len * Math.cos(a + side * Math.PI / 3)).toFixed(2)
                                      + " " + (by + R * len * Math.sin(a + side * Math.PI / 3)).toFixed(2)
                d += "M " + tip(-1) + " L " + bx.toFixed(2) + " " + by.toFixed(2) + " L " + tip(1) + " "
            }
        }
        return d
    }

    ParallelAnimation {
        id: burstAnim
        NumberAnimation {
            target: crystal; property: "scale"; from: 0.18; to: 1
            duration: 450; easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: crystal; property: "rotation"; from: -8; to: 6
            duration: 450; easing.type: Easing.OutCubic
        }
        SequentialAnimation {
            NumberAnimation { target: crystal; property: "opacity"; from: 0; to: 0.9; duration: 40 }
            PauseAnimation { duration: 70 }
            NumberAnimation {
                target: crystal; property: "opacity"; to: 0
                duration: 340; easing.type: Easing.InOutQuad
            }
        }
    }
}
