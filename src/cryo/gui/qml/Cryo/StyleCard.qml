import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A style in the Settings picker: a small live preview drawn from that
// style's own tokens (window, wash, a panel with text, a slider, a switch,
// the accent and secondary dots), its name and one line about it. The
// preview shows the accent the style would really draw with, override
// included. The card itself sits in the current style.
Rectangle {
    id: card
    required property string styleKey
    readonly property var st: Theme.styles[styleKey]
    readonly property bool selected: Theme.styleName === styleKey
    readonly property color previewAccent: Theme.accentFor(styleKey)
    signal picked()

    implicitHeight: cardColumn.implicitHeight + 20
    radius: 10
    color: Theme.panel
    border.width: selected ? 2 : 1
    border.color: selected ? Theme.accent : hover.hovered ? Theme.muted : Theme.panelBorder
    Accessible.role: Accessible.RadioButton
    Accessible.name: Theme.styleLabels[styleKey]
    Accessible.checked: selected

    ColumnLayout {
        id: cardColumn
        x: 10; y: 10
        width: parent.width - 20
        spacing: 8

        // ---- preview ----
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 66
            radius: 6
            color: card.st.bg
            border.color: card.st.panelBorder
            clip: true
            Rectangle {
                // the backdrop wash
                anchors.fill: parent
                anchors.margins: 1
                radius: 5
                gradient: Gradient {
                    GradientStop { position: 0.0; color: card.st.washColdA }
                    GradientStop { position: 0.8; color: "transparent" }
                }
            }
            Rectangle {
                // a panel with a title, a line of text and a slider
                id: miniPanel
                x: 8; y: 8
                width: parent.width - 16
                height: parent.height - 16
                radius: 4
                color: card.st.panel
                border.color: card.st.panelBorder
                Rectangle { x: 7; y: 8; width: Math.min(38, parent.width * 0.3); height: 4; radius: 2; color: card.st.fg }
                Rectangle { x: 7; y: 17; width: Math.min(58, parent.width * 0.45); height: 3; radius: 1.5; color: card.st.muted }
                Rectangle {
                    x: 7; y: parent.height - 12
                    width: parent.width - 14; height: 3; radius: 1.5
                    color: card.st.track
                    Rectangle {
                        width: parent.width * 0.62; height: parent.height; radius: 1.5
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: card.st.accent2 }
                            GradientStop { position: 1.0; color: card.previewAccent }
                        }
                    }
                    Rectangle {
                        x: parent.width * 0.62 - 3; y: -2
                        width: 7; height: 7; radius: 3.5
                        color: card.st.knob
                        border.color: card.previewAccent
                        border.width: 1.5
                    }
                }
                Rectangle {
                    // a switch, on
                    anchors.right: parent.right; anchors.rightMargin: 7
                    y: 7
                    width: 20; height: 11; radius: 5.5
                    color: Qt.alpha(card.previewAccent, 0.35)
                    border.color: card.previewAccent
                    Rectangle {
                        anchors.right: parent.right; anchors.rightMargin: 2
                        anchors.verticalCenter: parent.verticalCenter
                        width: 7; height: 7; radius: 3.5
                        color: card.previewAccent
                    }
                }
                Row {
                    // accent and secondary
                    anchors.right: parent.right; anchors.rightMargin: 7
                    y: 23
                    spacing: 4
                    Rectangle { width: 6; height: 6; radius: 3; color: card.previewAccent }
                    Rectangle { width: 6; height: 6; radius: 3; color: card.st.accent2 }
                }
            }
        }

        // ---- name and line ----
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Label {
                Layout.fillWidth: true
                text: Theme.styleLabels[card.styleKey]
                color: Theme.fg
                font.pixelSize: 13
                font.weight: Font.Medium
                elide: Text.ElideRight
            }
            Icon {
                visible: card.selected
                name: "check"
                size: 14
                color: Theme.accent
            }
        }
        Label {
            Layout.fillWidth: true
            Layout.topMargin: -5
            text: Theme.styleBlurbs[card.styleKey]
            color: Theme.muted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        onTapped: {
            Sfx.play("tap")
            card.picked()
        }
    }
}
