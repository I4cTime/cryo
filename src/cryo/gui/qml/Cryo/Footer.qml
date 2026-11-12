import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The bottom of the home column. With the Frost status line on (Prefs, the
// default) it shows Frost's one-line read on the machine (daemon.frostLine,
// rule-based in cryo/gui/voice.py), crossfading when the wording changes
// and updating in place when only the numbers do. Off, it shows the plain
// daemon status. Unreachable, the start command is always shown.
ColumnLayout {
    id: footer
    Layout.fillWidth: true
    Layout.topMargin: 2
    spacing: 4

    readonly property bool frostOn: Prefs.frostLine
    readonly property string statusText: daemon.connected
        ? "cryod · " + daemon.profile + " profile"
        : "cryod unreachable - is the service running?  sudo systemctl start cryod"

    // ---- Frost ----
    Item {
        objectName: "footerFrost"
        visible: footer.frostOn
        Layout.fillWidth: true
        implicitHeight: frostRow.height
        Row {
            id: frostRow
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 6
            readonly property real textRoom: Math.max(0, parent.width - frostIcon.width - spacing)

            Icon {
                id: frostIcon
                anchors.verticalCenter: parent.verticalCenter
                name: "snowflake"
                size: 11
                color: daemon.connected ? Theme.accent : Theme.muted
            }
            Item {
                id: lineBox
                width: Math.min(frostRow.textRoom, frostText.implicitWidth)
                height: frostText.implicitHeight
                Behavior on width {
                    enabled: Ambient.motion
                    NumberAnimation { duration: 220; easing.type: Easing.OutCubic }
                }
                Label {
                    id: ghostText
                    objectName: "footerFrostGhost"
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    opacity: 0
                    visible: opacity > 0
                    color: Theme.muted
                    font.pixelSize: 11
                }
                Label {
                    id: frostText
                    objectName: "footerFrostText"
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    text: daemon.frostLine
                    color: Theme.muted
                    font.pixelSize: 11
                }
            }
        }
    }
    ParallelAnimation {
        id: lineFade
        NumberAnimation { target: ghostText; property: "opacity"; from: 1; to: 0; duration: 220 }
        NumberAnimation { target: frostText; property: "opacity"; from: 0; to: 1; duration: 220 }
    }
    // What was on screen, so a new wording can fade in over the old one.
    property string _shownKey
    property string _shownText
    Component.onCompleted: {
        _shownKey = daemon.frostLineKey
        _shownText = daemon.frostLine
    }
    Connections {
        target: daemon
        function onFrostLineChanged() {
            if (daemon.frostLineKey !== footer._shownKey && footer.frostOn && Ambient.motion) {
                ghostText.text = footer._shownText
                lineFade.restart()
            }
            footer._shownKey = daemon.frostLineKey
            footer._shownText = daemon.frostLine
        }
    }

    // ---- plain status (Frost off), and the way back when unreachable ----
    Label {
        objectName: "footerStatus"
        visible: !footer.frostOn || !daemon.connected
        Layout.fillWidth: true
        text: footer.frostOn ? "sudo systemctl start cryod" : footer.statusText
        color: Theme.muted
        font.pixelSize: 10
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }
}
