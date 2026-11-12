import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The Settings view. Main.qml shows it when the window's page is
// "settings"; `back` (the close button or Escape) returns home. Everything
// here reads and writes the Prefs singleton, which persists on its own, so
// there is no apply step. Same margins, rhythm and section titles as the
// home column.
FocusScope {
    id: page
    signal back()
    focus: true
    Keys.onEscapePressed: page.back()

    readonly property var soundSets: [
        { key: "ice", label: "Ice", blurb: "Bright crystalline ticks." },
        { key: "glass", label: "Glass", blurb: "Soft chimes." },
        { key: "deep", label: "Deep", blurb: "Low and minimal." }
    ]
    readonly property bool soundUsable: Prefs.soundEnabled && Sfx.available
    // Sub-controls line up with the row titles; the row icons form a gutter.
    readonly property real inset: 28              // SettingRow.gutter
    // The close button in page coordinates: the window frost keeps clear
    // of it (Main.qml), as it does of the gear on the home page.
    readonly property rect clearRect: Qt.rect(content.x + settingsHeader.x + closeButton.x,
                                              content.y + settingsHeader.y + closeButton.y - scroller.contentY,
                                              closeButton.width, closeButton.height)

    component Divider: Rectangle {
        Layout.fillWidth: true
        Layout.topMargin: 2
        Layout.bottomMargin: 2
        implicitHeight: 1
        color: Theme.panelBorder
    }

    Flickable {
        id: scroller
        objectName: "settingsScroller"
        anchors.fill: parent
        contentHeight: content.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
            id: content
            x: 20
            y: 20
            width: page.width - 40
            spacing: 18

            // ---- header ----
            // Same metrics as the home Header: the title sits where the mark
            // and wordmark are, and the close button exactly where the gear
            // is, so opening and closing Settings never moves the pointer.
            RowLayout {
                id: settingsHeader
                objectName: "settingsHeader"
                Layout.fillWidth: true
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label {
                        text: "SETTINGS"
                        color: Theme.fg
                        font.pixelSize: 26
                        font.bold: true
                        font.letterSpacing: 6
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "Saved as you change them."
                        color: Theme.muted
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                }
                IconButton {
                    id: closeButton
                    objectName: "settingsClose"
                    Layout.leftMargin: -4
                    name: "close"
                    tooltip: "Close (Esc)"
                    onClicked: page.back()
                }
            }

            // ---- appearance ----
            SectionTitle { text: "APPEARANCE" }
            GridLayout {
                objectName: "styleCards"
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 10
                Repeater {
                    model: Theme.styleNames
                    delegate: StyleCard {
                        required property string modelData
                        objectName: "styleCard_" + modelData
                        styleKey: modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1      // equal columns
                        onPicked: Prefs.style = modelData
                    }
                }
            }
            Panel {
                Layout.fillWidth: true
                implicitHeight: accentColumn.height + 28
                AccentPicker {
                    id: accentColumn
                    x: 14; y: 14
                    width: parent.width - 28
                }
            }

            // ---- effects ----
            SectionTitle { text: "EFFECTS" }
            Panel {
                Layout.fillWidth: true
                implicitHeight: fxColumn.height + 28
                ColumnLayout {
                    id: fxColumn
                    x: 14; y: 14
                    width: parent.width - 28
                    spacing: 10
                    SettingRow {
                        icon: "snowflake"
                        title: "Frost and thermal chrome"
                        description: "Frost at the edges, and backdrop washes that follow the machine's heat."
                        CryoSwitch {
                            objectName: "effectsSwitch"
                            checked: Prefs.effects
                            onToggled: Prefs.effects = checked
                        }
                    }
                    Divider {}
                    SettingRow {
                        icon: "motion"
                        title: "Reduce motion"
                        description: "Stops looping and sweeping animation."
                        CryoSwitch {
                            objectName: "reduceMotionSwitch"
                            checked: Prefs.reduceMotion
                            onToggled: Prefs.reduceMotion = checked
                        }
                    }
                }
            }

            // ---- sound ----
            SectionTitle { text: "SOUND" }
            Panel {
                Layout.fillWidth: true
                implicitHeight: soundColumn.height + 28
                ColumnLayout {
                    id: soundColumn
                    x: 14; y: 14
                    width: parent.width - 28
                    spacing: 10
                    SettingRow {
                        icon: Prefs.soundEnabled && Sfx.available ? "sound-on" : "sound-off"
                        title: "Interface sounds"
                        description: "Mode changes, Thermal Guard, connection and clicks."
                        CryoSwitch {
                            // Its cue goes around the setting: "toggle_on"
                            // after sound is on (Sfx holds it until the bank
                            // has loaded), "toggle_off" while it still is.
                            objectName: "soundSwitch"
                            cue: false
                            checked: Prefs.soundEnabled
                            onToggled: {
                                if (checked) {
                                    Prefs.soundEnabled = true
                                    Sfx.play("toggle_on")
                                } else {
                                    Sfx.play("toggle_off")
                                    Prefs.soundEnabled = false
                                }
                            }
                        }
                    }
                    RowLayout {
                        // capability honesty: say it when sound cannot work
                        objectName: "soundUnavailable"
                        visible: !Sfx.available
                        Layout.fillWidth: true
                        Layout.leftMargin: page.inset
                        spacing: 6
                        Icon { name: "info"; size: 13; color: Theme.warn }
                        Label {
                            Layout.fillWidth: true
                            text: "Sound is unavailable on this system."
                            color: Theme.muted
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                    Divider {}
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: page.inset
                        spacing: 6
                        enabled: page.soundUsable
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: "Sound set"
                                color: Theme.fg
                                opacity: page.soundUsable ? 1 : 0.5
                                font.pixelSize: 13
                            }
                            Item { Layout.fillWidth: true }
                            Label {
                                readonly property var chosen: page.soundSets.find(s => s.key === Prefs.soundSet)
                                text: chosen ? chosen.blurb : ""
                                color: Theme.muted
                                opacity: page.soundUsable ? 1 : 0.5
                                font.pixelSize: 11
                            }
                        }
                        Segmented {
                            objectName: "soundSetPicker"
                            Layout.topMargin: 2
                            model: page.soundSets
                            current: Prefs.soundSet
                            onPicked: key => Prefs.soundSet = key
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: page.inset
                        Layout.topMargin: 4
                        spacing: 12
                        enabled: page.soundUsable
                        Label {
                            text: "Volume"
                            color: Theme.fg
                            opacity: page.soundUsable ? 1 : 0.5
                            font.pixelSize: 13
                        }
                        CryoSlider {
                            objectName: "soundVolume"
                            opacity: page.soundUsable ? 1 : 0.4
                            from: 0; to: 100; stepSize: 5
                            value: Math.round(Prefs.soundVolume * 100)
                            onMoved: Prefs.soundVolume = value / 100
                        }
                        Mono {
                            Layout.preferredWidth: 38
                            horizontalAlignment: Text.AlignRight
                            text: Math.round(Prefs.soundVolume * 100) + "%"
                            color: Theme.fg
                            opacity: page.soundUsable ? 1 : 0.5
                            font.pixelSize: 12
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: page.inset
                        spacing: 8
                        enabled: page.soundUsable
                        Label {
                            Layout.fillWidth: true
                            text: "Preview"
                            color: Theme.fg
                            opacity: page.soundUsable ? 1 : 0.5
                            font.pixelSize: 13
                        }
                        CryoButton {
                            objectName: "previewMode"
                            icon: "play"
                            label: "Mode change"
                            clickSound: "mode"
                        }
                        CryoButton {
                            objectName: "previewFreeze"
                            icon: "play"
                            label: "Guard freeze"
                            clickSound: "freeze"
                        }
                    }
                }
            }

            // ---- frost ----
            SectionTitle { text: "FROST" }
            Panel {
                Layout.fillWidth: true
                implicitHeight: frostColumn.height + 28
                ColumnLayout {
                    id: frostColumn
                    x: 14; y: 14
                    width: parent.width - 28
                    spacing: 12
                    SettingRow {
                        icon: "voice"
                        title: "Status line"
                        description: "A one-line read on the machine in the footer."
                        CryoSwitch {
                            objectName: "frostLineSwitch"
                            checked: Prefs.frostLine
                            onToggled: Prefs.frostLine = checked
                        }
                    }
                    Rectangle {
                        // the line as it reads right now
                        objectName: "frostSample"
                        Layout.fillWidth: true
                        Layout.leftMargin: page.inset
                        implicitHeight: sampleRow.implicitHeight + 20
                        radius: 8
                        color: Theme.track
                        opacity: Prefs.frostLine ? 1 : 0.5
                        RowLayout {
                            id: sampleRow
                            x: 12; y: 10
                            width: parent.width - 24
                            spacing: 8
                            Icon {
                                Layout.alignment: Qt.AlignTop
                                Layout.topMargin: 2
                                name: "snowflake"
                                size: 12
                                color: Theme.accent
                            }
                            Label {
                                objectName: "frostSampleText"
                                Layout.fillWidth: true
                                text: daemon.frostLine
                                color: Theme.fg
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }

            // ---- about ----
            SectionTitle { text: "ABOUT" }
            Panel {
                objectName: "aboutPanel"
                Layout.fillWidth: true
                implicitHeight: aboutColumn.height + 28
                ColumnLayout {
                    id: aboutColumn
                    x: 14; y: 14
                    width: parent.width - 28
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Label {
                            text: "Cryo"
                            color: Theme.fg
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }
                        Mono {
                            objectName: "aboutVersion"
                            text: appVersion
                            color: Theme.muted
                            font.pixelSize: 12
                        }
                        Rectangle {
                            objectName: "demoMarker"
                            visible: daemon.demo
                            implicitWidth: demoText.implicitWidth + 12
                            implicitHeight: 18
                            radius: 4
                            color: Qt.alpha(Theme.accent2, 0.15)
                            border.color: Theme.accent2Text
                            Label {
                                id: demoText
                                anchors.centerIn: parent
                                text: "DEMO"
                                color: Theme.accent2Text
                                font.pixelSize: 9
                                font.bold: true
                                font.letterSpacing: 1.5
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    Label {
                        Layout.fillWidth: true
                        Layout.topMargin: -6
                        text: daemon.demo
                              ? "Running against a scripted daemon. Nothing touches the hardware."
                              : "Command center for Alienware and Dell G-Series laptops."
                        color: Theme.muted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                    Divider {}
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 16
                        rowSpacing: 6
                        Label { text: "Daemon"; color: Theme.muted; font.pixelSize: 12 }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Rectangle {
                                width: 7; height: 7; radius: 3.5
                                color: daemon.connected ? Theme.ok : Theme.hot
                            }
                            Label {
                                objectName: "aboutDaemon"
                                Layout.fillWidth: true
                                text: daemon.connected
                                      ? "cryod · " + daemon.profile + " profile"
                                      : "cryod unreachable - sudo systemctl start cryod"
                                color: Theme.fg
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                        }
                        Label { text: "Model"; color: Theme.muted; font.pixelSize: 12 }
                        Label {
                            objectName: "aboutModel"
                            Layout.fillWidth: true
                            text: daemon.modelName || "Not reported yet"
                            color: daemon.modelName ? Theme.fg : Theme.muted
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                    }
                    Divider {}
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        CryoButton {
                            objectName: "linkSite"
                            icon: "external-link"
                            label: "cryo.i4c.studio"
                            tooltip: "https://cryo.i4c.studio"
                            onClicked: Qt.openUrlExternally("https://cryo.i4c.studio")
                        }
                        CryoButton {
                            objectName: "linkSource"
                            icon: "external-link"
                            label: "github.com/I4cTime/cryo"
                            tooltip: "Source, issues and releases"
                            onClicked: Qt.openUrlExternally("https://github.com/I4cTime/cryo")
                        }
                    }
                }
            }
        }
    }
}
