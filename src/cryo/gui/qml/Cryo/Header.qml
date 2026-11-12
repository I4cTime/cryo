import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects

// Brand mark, name and model, status badges and the connection dot.
RowLayout {
    Layout.fillWidth: true
    spacing: 12
    Item {
        Layout.preferredWidth: 42
        Layout.preferredHeight: 42
        Image {
            // Frost-crystal brand mark. PNG rather than the SVG:
            // Qt's SVG renderer ignores the mark's blur filters, so
            // the pre-rendered raster carries the neon glow.
            id: brandMark
            anchors.fill: parent
            source: "../../assets/cryo-256.png"
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            visible: false
        }
        MultiEffect {
            // static bloom - rendered once
            source: brandMark
            anchors.fill: brandMark
            shadowEnabled: true
            shadowColor: Theme.accent
            shadowOpacity: 0.55
            shadowBlur: 0.8
            blurMax: 20
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        Label {
            text: "CRYO"
            font.pixelSize: 26
            font.bold: true
            font.letterSpacing: 6
            color: Theme.fg
        }
        Label {
            Layout.fillWidth: true
            text: daemon.modelName || "Alienware command center"
            color: Theme.muted
            font.pixelSize: 12
            elide: Text.ElideRight
        }
    }
    Badge {
        visible: daemon.guard
        text: "GUARD"
        tint: Theme.hot
        pulseName: "guardPulse"
    }
    Badge {
        visible: daemon.gaming
        text: "GAMING"
        tint: Theme.accent2
        ink: Theme.accent2Text
        pulseName: "gamingPulse"
    }
    Rectangle {
        id: connDot
        width: 10; height: 10; radius: 5
        color: daemon.connected ? Theme.ok : Theme.hot
        ToolTip.visible: dotArea.containsMouse
        ToolTip.text: daemon.connected ? "cryod connected" : "cryod unreachable"
        MouseArea { id: dotArea; anchors.fill: parent; hoverEnabled: true }
        Rectangle {
            id: connDotSrc
            anchors.fill: parent
            radius: 5
            color: connDot.color
            visible: false
        }
        MultiEffect {
            z: -1
            source: connDotSrc
            anchors.fill: connDotSrc
            shadowEnabled: true
            shadowColor: connDot.color
            shadowBlur: 0.8
            blurMax: 12
        }
    }
}
