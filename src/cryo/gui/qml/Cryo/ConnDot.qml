import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

// cryod connection dot with a soft glow and a tooltip.
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
        shadowOpacity: Theme.glow
        shadowBlur: 0.8
        blurMax: 12
    }
}
