import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects

// Lighting: keyboard preview, effects, colour, brightness.
ColumnLayout {
    id: section
    Layout.fillWidth: true
    spacing: 18
    visible: daemon.hasLighting

    SectionTitle { text: "LIGHTING"; visible: daemon.hasLighting }
    Panel {
        visible: daemon.hasLighting
        Layout.fillWidth: true
        implicitHeight: lightColumn.height + 28
        ColumnLayout {
            id: lightColumn
            x: 14; y: 14
            width: parent.width - 28
            spacing: 10

            // Seeded from daemon config; a swatch click takes over.
            property string currentColor: daemon.lightColor

            KbdPreview {
                objectName: "kbdPreview"
                Layout.alignment: Qt.AlignHCenter
                Layout.bottomMargin: 4
                effect: daemon.lightEffect
                zoneColor: lightColumn.currentColor
                level: brightness.value
            }

            Flow {
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: [
                        { fx: "quantum",  label: "Quantum" },
                        { fx: "static",   label: "Static" },
                        { fx: "breathe",  label: "Breathe" },
                        { fx: "spectrum", label: "Spectrum" },
                        { fx: "rainbow",  label: "Rainbow" },
                        { fx: "wave",     label: "Wave" },
                        { fx: "backforth",label: "Bounce" },
                        { fx: "off",      label: "Off" }
                    ]
                    delegate: Rectangle {
                        id: fxChip
                        required property var modelData
                        readonly property bool active: modelData.fx === daemon.lightEffect
                        width: fxText.width + 22
                        height: 28
                        radius: 14
                        color: active ? Qt.alpha(Theme.accent, 0.10) : Theme.panel
                        border.color: active ? Theme.accent : Theme.panelBorder
                        Rectangle {
                            id: fxHaloSrc
                            anchors.fill: parent
                            radius: fxChip.radius
                            color: "transparent"
                            border.color: Theme.accent
                            visible: false
                        }
                        MultiEffect {
                            // same neon halo as the active power mode
                            z: -1
                            visible: fxChip.active
                            source: fxHaloSrc
                            anchors.fill: fxHaloSrc
                            shadowEnabled: true
                            shadowColor: Theme.accent
                            shadowBlur: 0.7
                            blurMax: 12
                        }
                        Label {
                            id: fxText
                            anchors.centerIn: parent
                            text: fxChip.modelData.label
                            color: fxChip.active ? Theme.accent : Theme.fg
                            font.pixelSize: 11
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: daemon.setLighting(parent.modelData.fx, lightColumn.currentColor)
                        }
                    }
                }
            }

            RowLayout {
                spacing: 8
                Label { text: "Color"; color: Theme.muted; font.pixelSize: 11 }
                Repeater {
                    model: ["#00D1FF", "#7B2DFF", "#FF2D55", "#3DDC97", "#FFB300", "#F3F5F9"]
                    delegate: Rectangle {
                        required property string modelData
                        width: 22; height: 22; radius: 11
                        color: modelData
                        border.width: lightColumn.currentColor === modelData ? 2 : 0
                        border.color: Theme.fg
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            // apply straight away with the current
                            // effect; nobody expects to re-click the
                            // effect chip for a colour to take
                            onClicked: {
                                lightColumn.currentColor = parent.modelData
                                daemon.setLighting(daemon.lightEffect, parent.modelData)
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Brightness"; color: Theme.muted; font.pixelSize: 12; Layout.preferredWidth: 70 }
                CryoSlider {
                    id: brightness
                    value: daemon.lightBrightness
                    Binding on value { when: !brightness.pressed; value: daemon.lightBrightness }
                    onPressedChanged: if (!pressed) daemon.setBrightness(Math.round(value))
                }
                Label { text: Math.round(brightness.value) + "%"; color: Theme.fg; font.pixelSize: 12; font.features: { "tnum": 1 }; Layout.preferredWidth: 36 }
            }
        }
    }
}
