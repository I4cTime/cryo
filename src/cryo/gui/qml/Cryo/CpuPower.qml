import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// CPU power: turbo toggle + per-mode performance cap (0.4.0)
ColumnLayout {
    id: section
    Layout.fillWidth: true
    spacing: 18
    // first-show reveal (Crystallize.qml)
    opacity: reveal.t
    transform: Translate { y: reveal.rise }
    Crystallize { id: reveal; target: section; title: sectionTitle; order: 3 }
    visible: daemon.hasCpuCap || daemon.hasTurbo

    SectionTitle { id: sectionTitle; text: "CPU POWER"; visible: daemon.hasCpuCap || daemon.hasTurbo }
    Panel {
        Layout.fillWidth: true
        visible: daemon.hasCpuCap || daemon.hasTurbo
        implicitHeight: capColumn.height + 28
        ColumnLayout {
            id: capColumn
            x: 14; y: 14
            width: parent.width - 28
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                visible: daemon.hasTurbo
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Turbo Boost"; color: Theme.fg; font.pixelSize: 13 }
                    Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Off pins every core at its base clock - quiet and cool, slower."; color: Theme.muted; font.pixelSize: 11 }
                }
                CryoSwitch {
                    checked: daemon.turbo
                    Binding on checked { value: daemon.turbo }
                    onToggled: daemon.setTurbo(checked)
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.panelBorder; visible: daemon.hasTurbo && daemon.hasCpuCap; Layout.topMargin: 4; Layout.bottomMargin: 4 }
            RowLayout {
                Layout.fillWidth: true
                visible: daemon.hasCpuCap
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Performance cap per mode"; color: Theme.fg; font.pixelSize: 13 }
                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        // Every configured mode at a glance, so you don't have
                        // to switch modes to see what each one is capped at.
                        property var caps: daemon.cpuCapProfiles
                        text: {
                            const parts = []
                            for (const name of daemon.profiles) {
                                const pct = caps[name]
                                if (pct !== undefined && pct < 100)
                                    parts.push((Theme.profileLabels[name] || name) + " " + pct + "%")
                            }
                            return parts.length ? parts.join("  ·  ") : "No mode is capped yet - pick a mode, then drag."
                        }
                        color: Theme.muted
                        font.pixelSize: 11
                    }
                }
                CryoSwitch {
                    id: capSwitch
                    checked: daemon.cpuCapEnabled
                    Binding on checked { value: daemon.cpuCapEnabled }
                    onToggled: daemon.setCpuCapEnabled(checked)
                }
            }
            Label {
                // Machine-specific: the GHz figure comes from this
                // CPU's cpufreq max, never from a fixed model.
                visible: daemon.hasCpuCap
                text: "Caps the CPU's top performance state (intel_pstate max_perf_pct); remembered per mode, re-applied on every switch and after resume. "
                      + (daemon.cpuMaxMhz > 0
                         ? "This CPU tops out at " + (daemon.cpuMaxMhz / 1000).toFixed(1) + " GHz; a lower cap trades a little single-core speed for less heat and power."
                         : "A lower cap trades a little single-core speed for less heat and power.")
                color: Theme.muted
                font.pixelSize: 11
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                visible: daemon.hasCpuCap
                enabled: capSwitch.checked
                opacity: enabled ? 1.0 : 0.4
                Label {
                    text: daemon.hasProfiles ? (Theme.profileLabels[daemon.profile] || daemon.profile) : "Default"
                    color: Theme.muted
                    font.pixelSize: 12
                    Layout.preferredWidth: 90
                    elide: Text.ElideRight
                }
                CryoSlider {
                    id: capSlider
                    from: 50; to: 100; stepSize: 1
                    value: daemon.cpuCap
                    Binding on value { when: !capSlider.pressed; value: daemon.cpuCap }
                    onPressedChanged: if (!pressed) daemon.setCpuCap(Math.round(value))
                }
                Label {
                    font.features: { "tnum": 1 }
                    text: Math.round(capSlider.value) + "%"
                          + (daemon.cpuMaxMhz > 0
                             ? "  ≈ " + (Math.round(capSlider.value) / 100 * daemon.cpuMaxMhz / 1000).toFixed(1) + " GHz"
                             : "")
                    color: Theme.fg
                    font.pixelSize: 12
                    Layout.preferredWidth: 100
                }
            }
        }
    }
}
