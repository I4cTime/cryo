import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Fan control: curves switch, manual boost, curve + guard editor.
ColumnLayout {
    id: section
    Layout.fillWidth: true
    spacing: 18
    // first-show reveal (Crystallize.qml)
    opacity: reveal.t
    transform: Translate { y: reveal.rise }
    Crystallize { id: reveal; target: section; title: sectionTitle; order: 2 }
    visible: daemon.hasThermals

    function fanBoost(group) {
        for (const f of daemon.fans)
            if (f.group === group) return f.boost
        return 0
    }

    SectionTitle { id: sectionTitle; text: "FAN CONTROL"; visible: daemon.hasThermals }
    Panel {
        Layout.fillWidth: true
        visible: daemon.hasThermals
        implicitHeight: fanColumn.height + 28
        ColumnLayout {
            id: fanColumn
            x: 14; y: 14
            width: parent.width - 28
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Automatic fan curves"; color: Theme.fg; font.pixelSize: 13 }
                    Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Off = manual boost sliders"; color: Theme.muted; font.pixelSize: 11 }
                }
                CryoSwitch {
                    id: curvesSwitch
                    enabled: daemon.hasBoost
                    // Mirrors daemon config (re-asserted every tick):
                    // stays truthful across restarts and when a manual
                    // boost drag disables curves daemon-side.
                    checked: daemon.curvesEnabled
                    Binding on checked { value: daemon.curvesEnabled }
                    onToggled: daemon.setCurvesEnabled(checked)
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Label {
                    text: !daemon.hasBoost
                          ? "Fan boost is not supported by this model's firmware - curves and manual boost are unavailable."
                          : daemon.profile === "custom"
                          ? (curvesSwitch.checked
                             ? "Curves active - boosts follow temperature."
                             : "Manual boost - drag the sliders.")
                          : "Fans follow the firmware in this mode. Custom mode hands them to Cryo."
                    color: daemon.hasBoost ? Theme.muted : Theme.warn
                    font.pixelSize: 11
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }
                CryoButton {
                    label: "Use Custom mode"
                    accent: true
                    visible: daemon.hasBoost && daemon.hasProfiles && daemon.profile !== "custom"
                    onClicked: daemon.setProfile("custom")
                }
            }
            RowLayout {
                Layout.fillWidth: true
                enabled: daemon.hasBoost && daemon.profile === "custom" && !curvesSwitch.checked
                opacity: enabled ? 1.0 : 0.4
                Label { text: "CPU boost"; color: Theme.muted; font.pixelSize: 12; Layout.preferredWidth: 70 }
                CryoSlider {
                    id: cpuBoost
                    value: section.fanBoost("cpu")
                    // Keep tracking telemetry after a drag (plain
                    // `value:` bindings break on user interaction).
                    Binding on value { when: !cpuBoost.pressed; value: section.fanBoost("cpu") }
                    onPressedChanged: if (!pressed) daemon.setBoost("cpu", Math.round(value))
                }
                Label { text: Math.round(cpuBoost.value) + "%"; color: Theme.fg; font.pixelSize: 12; font.features: { "tnum": 1 }; Layout.preferredWidth: 36 }
            }
            RowLayout {
                Layout.fillWidth: true
                enabled: daemon.hasBoost && daemon.profile === "custom" && !curvesSwitch.checked
                opacity: enabled ? 1.0 : 0.4
                Label { text: "GPU boost"; color: Theme.muted; font.pixelSize: 12; Layout.preferredWidth: 70 }
                CryoSlider {
                    id: gpuBoost
                    value: section.fanBoost("gpu")
                    Binding on value { when: !gpuBoost.pressed; value: section.fanBoost("gpu") }
                    onPressedChanged: if (!pressed) daemon.setBoost("gpu", Math.round(value))
                }
                Label { text: Math.round(gpuBoost.value) + "%"; color: Theme.fg; font.pixelSize: 12; font.features: { "tnum": 1 }; Layout.preferredWidth: 36 }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.panelBorder; Layout.topMargin: 6; visible: daemon.hasBoost }
            RowLayout {
                Layout.fillWidth: true
                visible: daemon.hasBoost
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Curves & Thermal Guard"; color: Theme.fg; font.pixelSize: 13 }
                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: curveBody.visible
                              ? "Points are °C → boost %. Curves apply in Custom mode; the guard trips in any mode."
                              : "Edit the curve points and the guard's trip temperatures."
                        color: Theme.muted
                        font.pixelSize: 11
                    }
                }
                CryoButton {
                    label: curveBody.visible ? "Done" : "Edit"
                    onClicked: curveBody.visible = !curveBody.visible
                }
            }
            ColumnLayout {
                id: curveBody
                objectName: "curveBody"
                visible: false
                enabled: daemon.hasBoost
                Layout.fillWidth: true
                spacing: 12
                CurveEditor { group: "cpu"; source: daemon.cpuCurve }
                CurveEditor { group: "gpu"; source: daemon.gpuCurve }

                // Tuning + guard thresholds
                ColumnLayout {
                    id: tuning
                    Layout.fillWidth: true
                    spacing: 6
                    property bool dirty: false
                    function load() {
                        hystSpin.value = Math.round(daemon.curveHysteresis)
                        stepSpin.value = daemon.curveMinStep
                        cpuTripSpin.value = daemon.guardCpuTrip
                        gpuTripSpin.value = daemon.guardGpuTrip
                        releaseSpin.value = daemon.guardRelease
                        tuning.dirty = false
                    }
                    Connections {
                        target: daemon
                        function onConfigChanged() { if (!tuning.dirty) tuning.load() }
                    }
                    Component.onCompleted: load()
                    Label { text: "Tuning & Thermal Guard"; color: Theme.fg; font.pixelSize: 12; font.bold: true }
                    GridLayout {
                        columns: 4
                        columnSpacing: 8
                        rowSpacing: 6
                        Layout.fillWidth: true
                        Label { text: "Hysteresis °C"; color: Theme.muted; font.pixelSize: 11 }
                        CryoSpin { id: hystSpin; from: 0; to: 15; onValueModified: tuning.dirty = true }
                        Label { text: "Min step %"; color: Theme.muted; font.pixelSize: 11 }
                        CryoSpin { id: stepSpin; from: 1; to: 25; onValueModified: tuning.dirty = true }
                        Label { text: "CPU trip °C"; color: Theme.muted; font.pixelSize: 11 }
                        CryoSpin { id: cpuTripSpin; from: 60; to: 105; onValueModified: tuning.dirty = true }
                        Label { text: "GPU trip °C"; color: Theme.muted; font.pixelSize: 11 }
                        CryoSpin { id: gpuTripSpin; from: 60; to: 105; onValueModified: tuning.dirty = true }
                        Label { text: "Release °C"; color: Theme.muted; font.pixelSize: 11 }
                        CryoSpin { id: releaseSpin; from: 1; to: 30; onValueModified: tuning.dirty = true }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        CryoButton { label: "Revert"; enabled: tuning.dirty; onClicked: tuning.load() }
                        Item { Layout.fillWidth: true }
                        CryoButton {
                            label: "Apply"
                            accent: true
                            enabled: tuning.dirty
                            onClicked: {
                                daemon.setCurveTuning(hystSpin.value, stepSpin.value)
                                daemon.setGuard(cpuTripSpin.value, gpuTripSpin.value, releaseSpin.value)
                                tuning.dirty = false
                            }
                        }
                    }
                }
            }
        }
    }
}
