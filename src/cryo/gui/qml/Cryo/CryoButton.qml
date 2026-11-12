import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    id: btn
    property string label
    property bool accent: false
    signal clicked()
    implicitHeight: 28
    implicitWidth: btnText.implicitWidth + 24
    radius: 6
    color: accent ? Qt.alpha(Theme.accent, 0.15) : Theme.track
    border.color: accent ? Theme.accent : Theme.panelBorder
    opacity: enabled ? 1.0 : 0.4
    Label {
        id: btnText
        anchors.centerIn: parent
        text: btn.label
        color: btn.accent ? Theme.accent : Theme.fg
        font.pixelSize: 12
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
}
