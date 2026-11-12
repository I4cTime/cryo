import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Daemon error banner - transient; daemon-side command failures
// (e.g. a rejected sysfs write) surface here instead of silently
// doing nothing.
Rectangle {
    visible: errorText.text !== ""
    Layout.fillWidth: true
    implicitHeight: errorText.implicitHeight + 16
    radius: 8
    color: Qt.alpha(Theme.hot, 0.12)
    border.color: Theme.hot
    border.width: 1
    Label {
        id: errorText
        anchors.fill: parent
        anchors.margins: 8
        text: ""
        color: Theme.hot
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        verticalAlignment: Text.AlignVCenter
    }
    Timer {
        id: errorClear
        interval: 6000
        onTriggered: errorText.text = ""
    }
    Connections {
        target: daemon
        function onErrorOccurred(message) {
            errorText.text = "cryod: " + message
            errorClear.restart()
        }
    }
}
