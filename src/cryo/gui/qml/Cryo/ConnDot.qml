import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

// cryod connection dot with a soft glow and a tooltip. Connected, the halo
// breathes slowly (2.6 s, only while motion is allowed); disconnected it is
// a steady red dot.
Rectangle {
    id: connDot
    width: 10; height: 10; radius: 5
    color: daemon.connected ? Theme.ok : Theme.hot
    ToolTip.visible: dotArea.containsMouse
    ToolTip.text: daemon.connected ? "cryod connected" : "cryod unreachable"
    MouseArea { id: dotArea; anchors.fill: parent; hoverEnabled: true }

    // 0..1 breath; held at 1 whenever the loop is not running.
    property real breath: 1
    SequentialAnimation on breath {
        objectName: "connBreath"
        running: Ambient.motion && daemon.connected && connDot.visible
        loops: Animation.Infinite
        NumberAnimation { to: 0.25; duration: 1300; easing.type: Easing.InOutSine }
        NumberAnimation { to: 1.0; duration: 1300; easing.type: Easing.InOutSine }
        onRunningChanged: if (!running) connDot.breath = 1
    }

    Rectangle {
        id: connDotSrc
        anchors.fill: parent
        radius: 5
        color: connDot.color
        visible: false
    }
    MultiEffect {
        // opacity and scale only: the blur itself is rendered once
        z: -1
        source: connDotSrc
        anchors.fill: connDotSrc
        opacity: 0.45 + 0.55 * connDot.breath
        scale: 0.85 + 0.3 * connDot.breath
        shadowEnabled: true
        shadowColor: connDot.color
        shadowOpacity: Theme.glow
        shadowBlur: 0.8
        blurMax: 12
    }
}
