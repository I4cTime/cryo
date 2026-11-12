import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Shapes

// Small fan whose rotor turns in proportion to the real RPM (~0.12°/s
// per rpm reads as spinning without strobing) and stops dead at 0.
Item {
    id: fanGlyph
    property int rpm
    property color tint: Theme.accent
    property string animName          // objectName of the spin driver (for tests)
    implicitWidth: 20
    implicitHeight: 20
    readonly property color ink: rpm > 0 ? tint : Theme.muted

    Item {
        // 24-unit design grid scaled to the glyph size
        width: 24
        height: 24
        anchors.centerIn: parent
        scale: fanGlyph.width / 24

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Qt.alpha(fanGlyph.ink, 0.45)
                strokeWidth: 1.4
                fillColor: "transparent"
                PathAngleArc { centerX: 12; centerY: 12; radiusX: 11.2; radiusY: 11.2; startAngle: 0; sweepAngle: 360 }
            }
        }
        Shape {
            id: rotor
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            // one ShapePath per blade: the curve renderer drops repeated
            // subpaths that start at the same point
            ShapePath {
                strokeColor: "transparent"
                fillColor: fanGlyph.ink
                PathSvg { path: "M 10.4 9.23 C 8.75 6.37 10 2.61 13.36 2.3 C 15.75 2.73 18.3 4.49 19.09 6.46 C 16.82 6.25 13.87 7.36 13.09 8.99 Z" }
            }
            ShapePath {
                strokeColor: "transparent"
                fillColor: fanGlyph.ink
                PathSvg { path: "M 14.77 10.4 C 17.63 8.75 21.39 10 21.7 13.36 C 21.27 15.75 19.51 18.3 17.54 19.09 C 17.75 16.82 16.64 13.87 15.01 13.09 Z" }
            }
            ShapePath {
                strokeColor: "transparent"
                fillColor: fanGlyph.ink
                PathSvg { path: "M 13.6 14.77 C 15.25 17.63 14 21.39 10.64 21.7 C 8.25 21.27 5.7 19.51 4.91 17.54 C 7.18 17.75 10.13 16.64 10.91 15.01 Z" }
            }
            ShapePath {
                strokeColor: "transparent"
                fillColor: fanGlyph.ink
                PathSvg { path: "M 9.23 13.6 C 6.37 15.25 2.61 14 2.3 10.64 C 2.73 8.25 4.49 5.7 6.46 4.91 C 6.25 7.18 7.36 10.13 8.99 10.91 Z" }
            }
            ShapePath {
                strokeColor: fanGlyph.ink
                strokeWidth: 1.2
                fillColor: Theme.panel
                PathAngleArc { centerX: 12; centerY: 12; radiusX: 2.4; radiusY: 2.4; startAngle: 0; sweepAngle: 360 }
            }
        }
    }
    FrameAnimation {
        objectName: fanGlyph.animName
        running: Ambient.motion && fanGlyph.visible && fanGlyph.rpm > 0
        onTriggered: rotor.rotation = (rotor.rotation + fanGlyph.rpm * 0.12 * Math.min(frameTime, 0.1)) % 360
    }
}
