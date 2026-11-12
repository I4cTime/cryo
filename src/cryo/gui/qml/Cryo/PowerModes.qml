import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Power modes - rendered from the daemon's capability list, so
// Legacy-profile or no-G-Mode machines see exactly what exists.
ColumnLayout {
    Layout.fillWidth: true
    spacing: 18

    SectionTitle { text: "POWER MODES"; visible: daemon.hasProfiles }
    // All modes on one row: compact, still glowing when active.
    RowLayout {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: daemon.profiles
            delegate: ModeButton {
                required property string modelData
                name: modelData
                icon: Theme.profileIcons[modelData] ?? "mode-custom"
                label: Theme.profileLabels[modelData]
                       ?? (modelData.charAt(0).toUpperCase() + modelData.slice(1))
                shortLabel: Theme.profileShortLabels[modelData] ?? label
            }
        }
    }
}
