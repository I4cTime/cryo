import QtQuick
import QtQuick.Controls.Basic

// A bare icon you can click (the header gear, the Settings close button),
// with a tile that shows on hover.
Item {
    id: button
    property string name
    property string tooltip
    property real size: 18
    property color color: area.containsMouse ? Theme.fg : Theme.muted
    signal clicked()
    implicitWidth: size + 12
    implicitHeight: size + 12

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: area.containsMouse ? Theme.track : "transparent"
    }
    Icon {
        anchors.centerIn: parent
        name: button.name
        size: button.size
        color: button.color
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            Sfx.play("tap")
            button.clicked()
        }
    }
    ToolTip.visible: area.containsMouse && button.tooltip !== ""
    ToolTip.delay: 500
    ToolTip.text: button.tooltip
}
