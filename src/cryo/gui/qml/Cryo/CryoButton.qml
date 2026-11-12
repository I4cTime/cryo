import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    id: btn
    property string label
    property string icon              // icon name; shown instead of a label
    property string tooltip
    property bool accent: false
    signal clicked()
    implicitHeight: 28
    implicitWidth: btn.icon !== "" ? 28 : btnText.implicitWidth + 24
    radius: 6
    color: accent ? Qt.alpha(Theme.accent, 0.15) : Theme.track
    border.color: accent ? Theme.accent : Theme.panelBorder
    opacity: enabled ? 1.0 : 0.4
    Label {
        id: btnText
        anchors.centerIn: parent
        visible: btn.icon === ""
        text: btn.label
        color: btn.accent ? Theme.accent : Theme.fg
        font.pixelSize: 12
    }
    Icon {
        anchors.centerIn: parent
        visible: btn.icon !== ""
        name: btn.icon
        size: 14
        color: btn.accent ? Theme.accent : Theme.fg
    }
    MouseArea {
        id: btnArea
        anchors.fill: parent
        hoverEnabled: btn.tooltip !== ""
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
    ToolTip.visible: btnArea.containsMouse && btn.tooltip !== ""
    ToolTip.delay: 500
    ToolTip.text: btn.tooltip
}
