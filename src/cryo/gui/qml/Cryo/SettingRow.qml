import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// One Settings line: an optional icon, a title with a one-line explanation
// under it, and whatever control is declared inside (a switch, a chip) on
// the right, centred on the text block.
RowLayout {
    id: row
    // Where the title starts: icon (16) plus spacing (12). Content under a
    // row (pickers, sliders, samples) indents by this to line up with it.
    readonly property real gutter: 28
    property string title
    property string description
    property string icon
    default property alias trailing: slot.data
    Layout.fillWidth: true
    spacing: 12

    Icon {
        visible: row.icon !== ""
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: 1
        name: row.icon
        size: 16
        color: Theme.muted
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        Label {
            Layout.fillWidth: true
            text: row.title
            color: Theme.fg
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }
        Label {
            Layout.fillWidth: true
            visible: row.description !== ""
            text: row.description
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
    }
    RowLayout {
        id: slot
        Layout.alignment: Qt.AlignVCenter
        spacing: 8
    }
}
