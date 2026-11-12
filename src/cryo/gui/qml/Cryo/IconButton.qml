import QtQuick
import QtQuick.Controls.Basic

// An icon you can click: bare (header gear) or `boxed` on a panel-coloured
// tile (the Settings back button, which sits where frost gathers).
Item {
    id: button
    property string name
    property string tooltip
    property real size: 18
    property bool boxed: false
    property color color: area.containsMouse ? Theme.fg : Theme.muted
    signal clicked()
    implicitWidth: size + 12
    implicitHeight: size + 12

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: area.containsMouse ? Theme.track : button.boxed ? Theme.panel : "transparent"
        border.width: button.boxed ? 1 : 0
        border.color: area.containsMouse ? Theme.muted : Theme.panelBorder
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
