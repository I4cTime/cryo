import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Accent override: "Style default" or one of Theme.accentChoices, written to
// Prefs.accent. Each swatch shows the colour as this style will draw it
// (Theme.readableOn), so on a light style the pale ones appear deepened.
ColumnLayout {
    id: picker
    Layout.fillWidth: true
    spacing: 12

    SettingRow {
        id: accentRow
        icon: "palette"
        title: "Accent"
        description: "Highlights, switches and sliders."
        Rectangle {
            // "Style default" chip
            id: defaultChip
            objectName: "accentDefault"
            readonly property bool active: !Theme.accentOverridden
            implicitWidth: defaultRow.implicitWidth + 22
            implicitHeight: 28
            radius: 14
            color: active ? Qt.alpha(Theme.accent, 0.10) : Theme.panel
            border.color: active ? Theme.accent : Theme.panelBorder
            Accessible.role: Accessible.RadioButton
            Accessible.name: "Style default"
            Accessible.checked: active
            Row {
                id: defaultRow
                anchors.centerIn: parent
                spacing: 6
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 10; height: 10; radius: 5
                    color: Theme.styleAccent
                }
                Label {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Style default"
                    color: defaultChip.active ? Theme.accent : Theme.fg
                    font.pixelSize: 11
                }
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    Sfx.play("tap")
                    Prefs.accent = ""
                }
            }
        }
    }

    Item {
        // swatches spread edge to edge
        id: swatchBox
        Layout.fillWidth: true
        Layout.leftMargin: accentRow.gutter
        implicitHeight: 34
        readonly property int count: Theme.accentChoices.length
        readonly property real cell: 34
        Row {
            spacing: swatchBox.count > 1
                     ? Math.max(2, (swatchBox.width - swatchBox.count * swatchBox.cell) / (swatchBox.count - 1))
                     : 0
            Repeater {
                model: Theme.accentChoices
                delegate: Item {
                    id: swatch
                    required property var modelData
                    readonly property bool active: Theme.accentOverridden
                                                   && Prefs.accent.toUpperCase() === modelData.color.toUpperCase()
                    readonly property color shown: Theme.readableOn(modelData.color, Theme.panel)
                    objectName: "accent" + modelData.name
                    width: swatchBox.cell
                    height: swatchBox.cell
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: modelData.name
                    Accessible.checked: active
                    Rectangle {
                        // selection ring, with a gap to the swatch
                        anchors.fill: parent
                        radius: width / 2
                        color: "transparent"
                        border.width: 2
                        border.color: Theme.fg
                        visible: swatch.active
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 24; height: 24; radius: 12
                        color: swatch.shown
                        border.width: Theme.isLight || swatchArea.containsMouse ? 1 : 0
                        border.color: swatchArea.containsMouse ? Theme.fg : Theme.panelBorder
                        Icon {
                            anchors.centerIn: parent
                            visible: swatch.active
                            name: "check"
                            size: 12
                            color: Theme.panel
                        }
                    }
                    MouseArea {
                        id: swatchArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            Sfx.play("tap")
                            Prefs.accent = swatch.modelData.color
                        }
                    }
                    ToolTip.visible: swatchArea.containsMouse
                    ToolTip.delay: 400
                    ToolTip.text: swatch.modelData.name
                }
            }
        }
    }

    Label {
        // say so when the override is not drawn as picked
        Layout.fillWidth: true
        Layout.leftMargin: accentRow.gutter
        Layout.topMargin: -4
        visible: Theme.accentOverridden
                 && Theme.accent.toString().toUpperCase() !== Prefs.accent.toUpperCase()
        text: (Theme.isLight ? "Deepened" : "Lightened") + " on " + Theme.styleLabels[Theme.styleName]
              + " so it stays readable."
        color: Theme.muted
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }
}
