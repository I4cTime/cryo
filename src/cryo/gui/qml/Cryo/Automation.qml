import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Automation: auto-profile rules and the power source.
ColumnLayout {
    id: section
    Layout.fillWidth: true
    spacing: 18

    SectionTitle { text: "AUTOMATION" }
    Panel {
        Layout.fillWidth: true
        implicitHeight: autoColumn.height + 28
        ColumnLayout {
            id: autoColumn
            x: 14; y: 14
            width: parent.width - 28
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Auto profiles"; color: Theme.fg; font.pixelSize: 13 }
                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        // From the daemon's config, not a fixed string.
                        property var rules: daemon.autoRules
                        function label(name) { return name ? (Theme.profileLabels[name] || name) : "-" }
                        text: (daemon.hasGameSense ? "game → " + label(rules.on_game) + " · " : "")
                              + "battery → " + label(rules.on_battery)
                              + " · AC → " + label(rules.on_ac)
                        color: Theme.muted
                        font.pixelSize: 11
                    }
                }
                CryoSwitch {
                    checked: daemon.autoEnabled
                    Binding on checked { value: daemon.autoEnabled }
                    onToggled: daemon.setAutoEnabled(checked)
                }
            }
            RowLayout {
                spacing: 5
                Icon {
                    name: daemon.ac ? "plug" : "battery"
                    size: 13
                    color: Theme.muted
                }
                Label {
                    text: daemon.ac ? "On AC power" : "On battery"
                    color: Theme.muted
                    font.pixelSize: 11
                }
                Label {
                    visible: daemon.gaming
                    Layout.leftMargin: 4
                    text: "·"
                    color: Theme.muted
                    font.pixelSize: 11
                }
                Icon {
                    visible: daemon.gaming
                    Layout.leftMargin: 4
                    name: "gaming"
                    size: 13
                    color: Theme.muted
                }
                Label {
                    visible: daemon.gaming
                    text: "game detected"
                    color: Theme.muted
                    font.pixelSize: 11
                }
            }
        }
    }
}
