import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Settings view (stub). Main.qml shows it when the window's page is
// "settings"; `back` returns home. The Settings piece fills it in on top of
// the Prefs singleton (style, accent, effects, reduce motion, sound, Frost
// line) and an about block.
Item {
    id: page
    signal back()

    ColumnLayout {
        x: 20
        y: 20
        width: page.width - 40
        spacing: 18
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            IconButton {
                objectName: "settingsBack"
                name: "back"
                tooltip: "Back"
                color: Theme.fg
                onClicked: page.back()
            }
            Label {
                text: "SETTINGS"
                color: Theme.fg
                font.pixelSize: 18
                font.bold: true
                font.letterSpacing: 4
            }
        }
    }
}
