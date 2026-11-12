import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

// Header status pill with a pulsing neon halo.
Rectangle {
    id: badge
    property string text
    property color tint: Theme.hot
    property color ink: tint
    property string pulseName         // objectName of the pulse (for tests)
    // Opaque fill so the halo shows only outside the pill.
    color: Qt.tint(Theme.bg, Qt.alpha(tint, 0.22))
    border.color: ink
    radius: 6
    implicitWidth: badgeText.implicitWidth + 16
    implicitHeight: 24

    Rectangle {
        id: badgeHaloSrc
        anchors.fill: parent
        radius: badge.radius
        color: badge.tint
        visible: false
    }
    MultiEffect {
        id: badgeHalo
        z: -1
        source: badgeHaloSrc
        anchors.fill: badgeHaloSrc
        shadowEnabled: true
        shadowColor: badge.tint
        shadowBlur: 1.0
        blurMax: 20
        opacity: 0.35
        SequentialAnimation on opacity {
            objectName: badge.pulseName
            running: Ambient.motion && badge.visible
            loops: Animation.Infinite
            NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
            NumberAnimation { to: 0.35; duration: 900; easing.type: Easing.InOutSine }
        }
    }
    Label {
        id: badgeText
        anchors.centerIn: parent
        text: badge.text
        color: badge.ink
        font.pixelSize: 10
        font.bold: true
        font.letterSpacing: 2
    }
}
