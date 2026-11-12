import QtQuick
import QtQuick.Controls.Basic

Switch {
    id: sw
    opacity: enabled ? 1.0 : 0.4
    // Play the toggle cue (off for a switch that orders its own cue around
    // the setting it changes, like the sound switch).
    property bool cue: true
    // `toggled` fires only for user input, never for a binding update.
    onToggled: if (sw.cue) Sfx.play(sw.checked ? "toggle_on" : "toggle_off")
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
