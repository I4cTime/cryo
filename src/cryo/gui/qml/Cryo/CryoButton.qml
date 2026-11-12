import QtQuick
import QtQuick.Controls.Basic

// Text button, icon button (`icon` alone) or both (`icon` and `label`).
Rectangle {
    id: btn
    property string label
    property string icon              // icon name; with no label, an icon-only button
    property string tooltip
    property bool accent: false
    // Cue played on click ("" for none, e.g. a button that previews a sound).
    property string clickSound: "tap"
    signal clicked()
    readonly property bool _iconOnly: btn.icon !== "" && btn.label === ""
    implicitHeight: 28
    implicitWidth: _iconOnly ? 28 : btnRow.implicitWidth + 24
    radius: 6
    color: accent ? Qt.alpha(Theme.accent, 0.15) : Theme.track
    border.color: accent ? Theme.accent : Theme.panelBorder
    opacity: enabled ? 1.0 : 0.4
    Row {
        id: btnRow
        anchors.centerIn: parent
        spacing: 6
        Icon {
            anchors.verticalCenter: parent.verticalCenter
            visible: btn.icon !== ""
            name: btn.icon
            size: btn._iconOnly ? 14 : 12
            color: btn.accent ? Theme.accent : Theme.fg
        }
        Label {
            id: btnText
            anchors.verticalCenter: parent.verticalCenter
            visible: btn.label !== ""
            text: btn.label
            color: btn.accent ? Theme.accent : Theme.fg
            font.pixelSize: 12
        }
    }
    MouseArea {
        id: btnArea
        anchors.fill: parent
        hoverEnabled: btn.tooltip !== ""
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (btn.clickSound !== "")
                Sfx.play(btn.clickSound)
            btn.clicked()
        }
    }
    ToolTip.visible: btnArea.containsMouse && btn.tooltip !== ""
    ToolTip.delay: 500
    ToolTip.text: btn.tooltip
}
