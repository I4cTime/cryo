import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects

Rectangle {
    id: mode
    property string name
    property string icon             // name in assets/icons
    property string label            // full name (tooltip)
    property string shortLabel       // fits a 1/7th-width cell
    readonly property bool active: daemon.profile === name
    // Equal-width cells: every mode shares one row, whatever its label.
    Layout.fillWidth: true
    Layout.preferredWidth: 1
    Layout.minimumWidth: 0
    Layout.preferredHeight: 56
    radius: 12
    color: active ? Qt.alpha(Theme.accent, 0.10) : Theme.panel
    border.color: active ? Theme.accent : Theme.panelBorder
    border.width: active ? 2 : 1

    // Neon tube: a blurred copy of the active border, inside and out.
    Rectangle {
        id: modeHaloSrc
        anchors.fill: parent
        radius: mode.radius
        color: "transparent"
        border.color: Theme.accent
        border.width: 2
        visible: false
    }
    MultiEffect {
        z: -1
        source: modeHaloSrc
        anchors.fill: modeHaloSrc
        opacity: mode.active ? 1 : 0
        visible: opacity > 0
        shadowEnabled: true
        shadowColor: Theme.accent
        shadowOpacity: Theme.glow
        shadowBlur: 0.9
        blurMax: 20
        Behavior on opacity { enabled: Ambient.motion; NumberAnimation { duration: 200 } }
    }

    Column {
        anchors.centerIn: parent
        width: parent.width - 6
        spacing: 3
        Item {
            // Fixed box so the labels stay aligned under every icon.
            anchors.horizontalCenter: parent.horizontalCenter
            width: 20
            height: 20
            Icon {
                anchors.centerIn: parent
                name: mode.icon
                size: 18
                color: mode.active ? Theme.accent : Theme.muted
            }
        }
        Label {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: mode.shortLabel
            font.pixelSize: 10
            // Shrinks rather than clips if a cell gets narrower still.
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 8
            elide: Text.ElideRight
            font.weight: mode.active ? Font.Medium : Font.Normal
            color: mode.active ? Theme.fg : Theme.muted
        }
    }
    MouseArea {
        id: modeArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: daemon.setProfile(mode.name)
    }
    ToolTip.visible: modeArea.containsMouse && mode.shortLabel !== mode.label
    ToolTip.delay: 400
    ToolTip.text: mode.label
    Behavior on border.color { ColorAnimation { duration: 150 } }
    Behavior on color { ColorAnimation { duration: 150 } }
}
