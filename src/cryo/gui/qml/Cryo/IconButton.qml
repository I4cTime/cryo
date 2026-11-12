import QtQuick
import QtQuick.Controls.Basic

// An icon you can click, with a tile that shows on hover. `backed` makes it
// a round keycap (panel fill, panel border) for a button that sits straight
// on the backdrop, so it stands above the window frost in every style (the
// header gear, the Settings close button). The hit area is the same either
// way.
Item {
    id: button
    property string name
    property string tooltip
    property real size: 18
    property bool backed: false
    property color color: area.containsMouse ? Theme.fg : Theme.muted
    signal clicked()
    implicitWidth: size + 12
    implicitHeight: size + 12

    Rectangle {
        objectName: "keycap"
        anchors.fill: parent
        radius: button.backed ? width / 2 : 8
        color: area.containsMouse ? Theme.track
               : button.backed ? Theme.panel : "transparent"
        border.width: button.backed ? 1 : 0
        border.color: Theme.panelBorder
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
