import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

Rectangle {
    id: panelRect
    color: Theme.panel
    border.color: Theme.panelBorder
    border.width: 1
    radius: 12

    // Soft drop shadow. Blurs a hidden, content-free copy of the panel
    // shape, so it re-renders only when the panel resizes.
    Rectangle {
        id: panelShadowSrc
        anchors.fill: parent
        radius: panelRect.radius
        color: Theme.shadow
        visible: false
    }
    MultiEffect {
        z: -1
        source: panelShadowSrc
        anchors.fill: panelShadowSrc
        shadowEnabled: true
        shadowColor: Theme.shadow
        shadowOpacity: 0.9
        shadowBlur: 1.0
        blurMax: 24
        shadowVerticalOffset: 6
    }
}
