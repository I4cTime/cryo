import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A segmented picker: equal segments on a track, the current one raised and
// ringed in the accent. `model` is [{ key, label }]; `picked(key)` on click.
Rectangle {
    id: seg
    property var model: []
    property string current
    signal picked(string key)
    Layout.fillWidth: true
    implicitHeight: 32
    radius: 8
    color: Theme.track
    border.color: Theme.panelBorder
    opacity: enabled ? 1.0 : 0.4

    Row {
        x: 3; y: 3
        width: parent.width - 6
        height: parent.height - 6
        Repeater {
            model: seg.model
            delegate: Rectangle {
                id: part
                required property var modelData
                required property int index
                readonly property bool active: seg.current === modelData.key
                objectName: "segment_" + modelData.key
                width: parent.width / seg.model.length
                height: parent.height
                radius: 6
                color: active ? Theme.panel : "transparent"
                border.color: active ? Theme.accent : "transparent"
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checked: active
                Label {
                    anchors.centerIn: parent
                    text: part.modelData.label
                    color: part.active ? Theme.accent : partArea.containsMouse ? Theme.fg : Theme.muted
                    font.pixelSize: 12
                    font.weight: part.active ? Font.Medium : Font.Normal
                }
                MouseArea {
                    id: partArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (part.active)
                            return
                        Sfx.play("tap")
                        seg.picked(part.modelData.key)
                    }
                }
            }
        }
    }
}
