import QtQuick
import QtQuick.Controls.Basic

Switch {
    id: sw
    indicator: Rectangle {
        implicitWidth: 40; implicitHeight: 22; radius: 11
        x: sw.leftPadding
        y: parent.height / 2 - height / 2
        color: sw.checked ? Qt.alpha(Theme.accent, 0.35) : Theme.track
        border.color: sw.checked ? Theme.accent : Theme.panelBorder
        Rectangle {
            x: sw.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            width: 16; height: 16; radius: 8
            color: sw.checked ? Theme.accent : Theme.muted
            Behavior on x { NumberAnimation { duration: 120 } }
        }
    }
}
