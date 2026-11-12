import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Brand mark, name and model, status badges, the connection dot and the
// Settings gear.
RowLayout {
    id: header
    signal settingsClicked()
    Layout.fillWidth: true
    spacing: 12
    // z 1 here and on the wordmark: the subtitle's Clearing reaches under
    // both, and must stay below them.
    LivingMark {
        z: 1
        Layout.preferredWidth: 42
        Layout.preferredHeight: 42
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        Label {
            z: 1
            text: "CRYO"
            font.pixelSize: 26
            font.bold: true
            font.letterSpacing: 6
            color: Theme.fg
        }
        Label {
            Layout.fillWidth: true
            objectName: "headerSubtitle"
            text: daemon.modelName || "Alienware command center"
            color: Theme.muted
            font.pixelSize: 12
            elide: Text.ElideRight
            Clearing { objectName: "clearing" }
        }
    }
    Badge {
        id: guardBadge
        visible: daemon.guard
        text: "GUARD"
        icon: "guard"
        tint: Theme.hot
        pulseName: "guardPulse"
    }
    Badge {
        id: gamingBadge
        visible: daemon.gaming
        text: "GAMING"
        icon: "gaming"
        tint: Theme.accent2
        ink: Theme.accent2Text
        pulseName: "gamingPulse"
    }
    ConnDot { id: connDot }
    IconButton {
        id: gear
        objectName: "settingsButton"
        Layout.leftMargin: -4
        name: "settings"
        backed: true
        tooltip: "Settings"
        onClicked: header.settingsClicked()
    }
}
