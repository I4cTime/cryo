import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: root
    visible: true
    width: 480
    height: 860
    minimumWidth: 440
    title: daemon.modelName ? "Cryo — " + daemon.modelName : "Cryo"
    color: "#000102"

    // ---- quantum fluidity tokens (lib/palette.ts equivalents) ----
    readonly property color cyan: "#00D1FF"
    readonly property color violet: "#7B2DFF"
    readonly property color violetText: "#A082FF"
    readonly property color fg: "#F3F5F9"
    readonly property color muted: "#828690"
    readonly property color panel: "#090D14"
    readonly property color panelBorder: "#1A2233"

    // ---- power-mode presentation (grid renders daemon.profiles) ----
    readonly property var profileGlyphs: ({
        "cool": "❄", "quiet": "🌙", "balanced": "⚖", "performance": "🚀",
        "gmode": "👾", "custom": "🎛", "low-power": "🍃"
    })
    readonly property var profileLabels: ({
        "cool": "Cool", "quiet": "Quiet", "balanced": "Balanced",
        "performance": "Performance", "gmode": "G-Mode", "custom": "Custom",
        "low-power": "Low Power"
    })

    // ---------- reusable pieces ----------

    component SectionTitle: Text {
        color: root.muted
        font.pixelSize: 11
        font.letterSpacing: 2
        font.bold: true
    }

    component Panel: Rectangle {
        color: root.panel
        border.color: root.panelBorder
        border.width: 1
        radius: 12
    }

    component ModeButton: Rectangle {
        id: mode
        property string name
        property string glyph
        property string label
        readonly property bool active: daemon.profile === name
        Layout.fillWidth: true
        Layout.preferredHeight: 72
        radius: 12
        color: active ? Qt.alpha(root.cyan, 0.10) : root.panel
        border.color: active ? root.cyan : root.panelBorder
        border.width: active ? 2 : 1

        Column {
            anchors.centerIn: parent
            spacing: 4
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: mode.glyph
                font.pixelSize: 20
                color: mode.active ? root.cyan : root.muted
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: mode.label
                font.pixelSize: 11
                color: mode.active ? root.fg : root.muted
            }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: daemon.setProfile(mode.name)
        }
        Behavior on border.color { ColorAnimation { duration: 150 } }
        Behavior on color { ColorAnimation { duration: 150 } }
    }

    component StatTile: Panel {
        id: tile
        property string label
        property real temp
        property real peak: 0
        property int rpm
        property var history: []
        property color accent: root.cyan
        Layout.fillWidth: true
        Layout.preferredHeight: 110

        Canvas {
            id: spark
            anchors.fill: parent
            anchors.margins: 1
            opacity: 0.35
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                const h = tile.history
                if (!h || h.length < 2)
                    return
                ctx.strokeStyle = tile.accent
                ctx.lineWidth = 1.5
                ctx.beginPath()
                const lo = 30, hi = 100
                for (let i = 0; i < h.length; i++) {
                    const x = i / (h.length - 1) * width
                    const y = height - (Math.min(Math.max(h[i], lo), hi) - lo) / (hi - lo) * height
                    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
                }
                ctx.stroke()
            }
            Connections {
                target: daemon
                function onTelemetryChanged() { spark.requestPaint() }
            }
        }

        Column {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 16
            spacing: 2
            Text { text: tile.label; color: root.muted; font.pixelSize: 11; font.letterSpacing: 1.5 }
            Text {
                text: tile.temp > 0 ? tile.temp.toFixed(0) + "°C" : "—"
                color: tile.temp >= 85 ? "#FF5470" : root.fg
                font.pixelSize: 30
                font.bold: true
            }
            Text {
                text: tile.rpm + " rpm" + (tile.peak > 0 ? "  ·  peak " + tile.peak.toFixed(0) + "°" : "")
                color: tile.peak >= 88 ? "#FF5470" : root.muted
                font.pixelSize: 11
            }
        }
    }

    component CryoSlider: Slider {
        id: control
        from: 0; to: 100; stepSize: 1
        Layout.fillWidth: true
        background: Rectangle {
            x: control.leftPadding
            y: control.topPadding + control.availableHeight / 2 - height / 2
            width: control.availableWidth
            height: 5
            radius: 3
            color: "#141A26"
            Rectangle {
                width: control.visualPosition * parent.width
                height: parent.height
                radius: 3
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: root.violet }
                    GradientStop { position: 1.0; color: root.cyan }
                }
            }
        }
        handle: Rectangle {
            x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
            y: control.topPadding + control.availableHeight / 2 - height / 2
            width: 16; height: 16; radius: 8
            color: root.fg
            border.color: root.cyan
            border.width: 2
        }
    }

    component CryoSwitch: Switch {
        id: sw
        indicator: Rectangle {
            implicitWidth: 40; implicitHeight: 22; radius: 11
            x: sw.leftPadding
            y: parent.height / 2 - height / 2
            color: sw.checked ? Qt.alpha(root.cyan, 0.35) : "#141A26"
            border.color: sw.checked ? root.cyan : root.panelBorder
            Rectangle {
                x: sw.checked ? parent.width - width - 3 : 3
                anchors.verticalCenter: parent.verticalCenter
                width: 16; height: 16; radius: 8
                color: sw.checked ? root.cyan : root.muted
                Behavior on x { NumberAnimation { duration: 120 } }
            }
        }
    }

    // ---------- helpers ----------

    function fanRpm(group) {
        let total = 0, n = 0
        for (const f of daemon.fans)
            if (f.group === group) { total += f.rpm; n++ }
        return n ? Math.round(total / n) : 0
    }
    function fanBoost(group) {
        for (const f of daemon.fans)
            if (f.group === group) return f.boost
        return 0
    }

    // ---------- layout ----------

    Flickable {
        anchors.fill: parent
        contentHeight: content.height + 40
        clip: true

        ColumnLayout {
            id: content
            x: 20
            y: 20
            width: root.width - 40
            spacing: 18

            // Header
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Image {
                    // Frost-crystal brand mark. PNG rather than the SVG:
                    // Qt's SVG renderer ignores the mark's blur filters, so
                    // the pre-rendered raster carries the neon glow.
                    source: "../assets/cryo-256.png"
                    Layout.preferredWidth: 42
                    Layout.preferredHeight: 42
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }
                Column {
                    spacing: 2
                    Text {
                        text: "CRYO"
                        font.pixelSize: 26
                        font.bold: true
                        font.letterSpacing: 6
                        color: root.fg
                    }
                    Text {
                        text: daemon.modelName || "Alienware command center"
                        color: root.muted
                        font.pixelSize: 12
                    }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    visible: daemon.guard
                    radius: 6
                    color: Qt.alpha("#FF5470", 0.2)
                    border.color: "#FF5470"
                    width: guardText.width + 16
                    height: 24
                    Text {
                        id: guardText
                        anchors.centerIn: parent
                        text: "GUARD"
                        color: "#FF5470"
                        font.pixelSize: 10
                        font.bold: true
                        font.letterSpacing: 2
                    }
                }
                Rectangle {
                    visible: daemon.gaming
                    radius: 6
                    color: Qt.alpha(root.violet, 0.25)
                    border.color: root.violetText
                    width: gamingText.width + 16
                    height: 24
                    Text {
                        id: gamingText
                        anchors.centerIn: parent
                        text: "GAMING"
                        color: root.violetText
                        font.pixelSize: 10
                        font.bold: true
                        font.letterSpacing: 2
                    }
                }
                Rectangle {
                    width: 10; height: 10; radius: 5
                    color: daemon.connected ? "#3DDC97" : "#FF5470"
                    ToolTip.visible: dotArea.containsMouse
                    ToolTip.text: daemon.connected ? "cryod connected" : "cryod unreachable"
                    MouseArea { id: dotArea; anchors.fill: parent; hoverEnabled: true }
                }
            }

            // Daemon error banner — transient; daemon-side command failures
            // (e.g. a rejected sysfs write) surface here instead of silently
            // doing nothing.
            Rectangle {
                visible: errorText.text !== ""
                Layout.fillWidth: true
                implicitHeight: errorText.implicitHeight + 16
                radius: 8
                color: Qt.alpha("#FF5470", 0.12)
                border.color: "#FF5470"
                border.width: 1
                Text {
                    id: errorText
                    anchors.fill: parent
                    anchors.margins: 8
                    text: ""
                    color: "#FF5470"
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    verticalAlignment: Text.AlignVCenter
                }
                Timer {
                    id: errorClear
                    interval: 6000
                    onTriggered: errorText.text = ""
                }
                Connections {
                    target: daemon
                    function onErrorOccurred(message) {
                        errorText.text = "cryod: " + message
                        errorClear.restart()
                    }
                }
            }

            // Power modes — rendered from the daemon's capability list, so
            // Legacy-profile or no-G-Mode machines see exactly what exists.
            SectionTitle { text: "POWER MODES" }
            GridLayout {
                Layout.fillWidth: true
                columns: 3
                rowSpacing: 10
                columnSpacing: 10
                Repeater {
                    model: daemon.profiles
                    delegate: ModeButton {
                        required property string modelData
                        name: modelData
                        glyph: root.profileGlyphs[modelData] ?? "❖"
                        label: root.profileLabels[modelData]
                               ?? (modelData.charAt(0).toUpperCase() + modelData.slice(1))
                    }
                }
            }

            // Telemetry
            SectionTitle { text: "TELEMETRY" }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                StatTile {
                    label: "CPU"
                    temp: daemon.cpuTemp
                    peak: daemon.cpuPeak
                    rpm: root.fanRpm("cpu")
                    history: daemon.cpuHistory
                    accent: root.cyan
                }
                StatTile {
                    label: "GPU"
                    temp: daemon.gpuTemp
                    peak: daemon.gpuPeak
                    rpm: root.fanRpm("gpu")
                    history: daemon.gpuHistory
                    accent: root.violetText
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text { text: "dGPU load"; color: root.muted; font.pixelSize: 11 }
                Rectangle {
                    Layout.fillWidth: true
                    height: 5; radius: 3
                    color: "#141A26"
                    Rectangle {
                        width: parent.width * daemon.gpuUtil / 100
                        height: parent.height; radius: 3
                        color: root.violetText
                        Behavior on width { NumberAnimation { duration: 300 } }
                    }
                }
                Text { text: daemon.gpuUtil + "%"; color: root.fg; font.pixelSize: 11 }
            }

            // VRAM — sparkline scaled to the card's full capacity, so a
            // leak reads as a steady climb and healthy load as a plateau.
            // The per-process rows below it name the offender.
            Panel {
                visible: daemon.vramTotal > 0
                Layout.fillWidth: true
                implicitHeight: vramColumn.height + 24

                Canvas {
                    id: vramSpark
                    anchors.fill: parent
                    anchors.margins: 1
                    opacity: 0.35
                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.reset()
                        const h = daemon.vramHistory
                        if (!h || h.length < 2 || daemon.vramTotal <= 0)
                            return
                        ctx.strokeStyle = root.violetText
                        ctx.lineWidth = 1.5
                        ctx.beginPath()
                        for (let i = 0; i < h.length; i++) {
                            const x = i / (h.length - 1) * width
                            const y = height - Math.min(h[i] / daemon.vramTotal, 1) * height
                            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
                        }
                        ctx.stroke()
                    }
                    Connections {
                        target: daemon
                        function onTelemetryChanged() { vramSpark.requestPaint() }
                    }
                }

                ColumnLayout {
                    id: vramColumn
                    x: 16
                    y: 12
                    width: parent.width - 32
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Column {
                            spacing: 2
                            Text { text: "VRAM"; color: root.muted; font.pixelSize: 11; font.letterSpacing: 1.5 }
                            Text {
                                text: (daemon.vramUsed / 1024).toFixed(1) + " GB"
                                color: daemon.vramUsed / daemon.vramTotal >= 0.9 ? "#FF5470" : root.fg
                                font.pixelSize: 20
                                font.bold: true
                            }
                        }
                        Item { Layout.fillWidth: true }
                        Column {
                            spacing: 2
                            Text {
                                anchors.right: parent.right
                                text: "peak " + (daemon.vramPeak / 1024).toFixed(1)
                                      + " · of " + (daemon.vramTotal / 1024).toFixed(1) + " GB"
                                color: root.muted
                                font.pixelSize: 11
                            }
                            Text {
                                anchors.right: parent.right
                                visible: daemon.gpuPower > 0
                                text: daemon.gpuPower.toFixed(0) + " W · "
                                      + daemon.gpuClock + " MHz"
                                color: root.muted
                                font.pixelSize: 11
                            }
                        }
                    }

                    Repeater {
                        model: daemon.vramProcs
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 8
                            Text {
                                text: modelData.name
                                color: root.muted
                                font.pixelSize: 10
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }
                            Text {
                                text: (modelData.vram_mb / 1024).toFixed(1) + " GB"
                                color: root.fg
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }

            // Fan control
            SectionTitle { text: "FAN CONTROL" }
            Panel {
                Layout.fillWidth: true
                implicitHeight: fanColumn.height + 28
                ColumnLayout {
                    id: fanColumn
                    x: 14; y: 14
                    width: parent.width - 28
                    spacing: 4
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "Fan curves (custom mode)"
                            color: root.fg
                            font.pixelSize: 13
                        }
                        Item { Layout.fillWidth: true }
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
                    Text {
                        text: !daemon.hasBoost
                              ? "Fan boost is not supported by this model's firmware — curves and manual boost are unavailable."
                              : daemon.profile === "custom"
                              ? (curvesSwitch.checked
                                 ? "Curves active — boosts follow temperature."
                                 : "Manual boost — drag sliders below.")
                              : "Switch to Custom mode to control fans directly."
                        color: daemon.hasBoost ? root.muted : "#FFB300"
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        enabled: daemon.hasBoost && daemon.profile === "custom" && !curvesSwitch.checked
                        opacity: enabled ? 1.0 : 0.4
                        Text { text: "CPU boost"; color: root.muted; font.pixelSize: 12; Layout.preferredWidth: 70 }
                        CryoSlider {
                            id: cpuBoost
                            value: root.fanBoost("cpu")
                            // Keep tracking telemetry after a drag (plain
                            // `value:` bindings break on user interaction).
                            Binding on value { when: !cpuBoost.pressed; value: root.fanBoost("cpu") }
                            onPressedChanged: if (!pressed) daemon.setBoost("cpu", Math.round(value))
                        }
                        Text { text: Math.round(cpuBoost.value) + "%"; color: root.fg; font.pixelSize: 12; Layout.preferredWidth: 36 }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        enabled: daemon.hasBoost && daemon.profile === "custom" && !curvesSwitch.checked
                        opacity: enabled ? 1.0 : 0.4
                        Text { text: "GPU boost"; color: root.muted; font.pixelSize: 12; Layout.preferredWidth: 70 }
                        CryoSlider {
                            id: gpuBoost
                            value: root.fanBoost("gpu")
                            Binding on value { when: !gpuBoost.pressed; value: root.fanBoost("gpu") }
                            onPressedChanged: if (!pressed) daemon.setBoost("gpu", Math.round(value))
                        }
                        Text { text: Math.round(gpuBoost.value) + "%"; color: root.fg; font.pixelSize: 12; Layout.preferredWidth: 36 }
                    }
                }
            }

            // Automation
            SectionTitle { text: "AUTOMATION" }
            Panel {
                Layout.fillWidth: true
                implicitHeight: autoColumn.height + 28
                ColumnLayout {
                    id: autoColumn
                    x: 14; y: 14
                    width: parent.width - 28
                    spacing: 4
                    RowLayout {
                        Layout.fillWidth: true
                        Column {
                            spacing: 2
                            Text { text: "Auto profiles"; color: root.fg; font.pixelSize: 13 }
                            Text {
                                text: "game → G-Mode · battery → Quiet · AC → Balanced"
                                color: root.muted
                                font.pixelSize: 11
                            }
                        }
                        Item { Layout.fillWidth: true }
                        CryoSwitch {
                            checked: daemon.autoEnabled
                            Binding on checked { value: daemon.autoEnabled }
                            onToggled: daemon.setAutoEnabled(checked)
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: daemon.hasTurbo
                        Text { text: "CPU Turbo Boost"; color: root.fg; font.pixelSize: 13 }
                        Item { Layout.fillWidth: true }
                        CryoSwitch {
                            checked: daemon.turbo
                            onToggled: daemon.setTurbo(checked)
                        }
                    }
                    RowLayout {
                        spacing: 6
                        Text {
                            text: daemon.ac ? "⚡ AC power" : "🔋 On battery"
                            color: root.muted
                            font.pixelSize: 11
                        }
                    }
                }
            }

            // Lighting
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
                                color: active ? Qt.alpha(root.cyan, 0.10) : root.panel
                                border.color: active ? root.cyan : root.panelBorder
                                Text {
                                    id: fxText
                                    anchors.centerIn: parent
                                    text: fxChip.modelData.label
                                    color: fxChip.active ? root.cyan : root.fg
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
                        Text { text: "Color"; color: root.muted; font.pixelSize: 11 }
                        Repeater {
                            model: ["#00D1FF", "#7B2DFF", "#FF2D55", "#3DDC97", "#FFB300", "#F3F5F9"]
                            delegate: Rectangle {
                                required property string modelData
                                width: 22; height: 22; radius: 11
                                color: modelData
                                border.width: lightColumn.currentColor === modelData ? 2 : 0
                                border.color: root.fg
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: lightColumn.currentColor = parent.modelData
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Brightness"; color: root.muted; font.pixelSize: 12; Layout.preferredWidth: 70 }
                        CryoSlider {
                            id: brightness
                            value: daemon.lightBrightness
                            Binding on value { when: !brightness.pressed; value: daemon.lightBrightness }
                            onPressedChanged: if (!pressed) daemon.setBrightness(Math.round(value))
                        }
                        Text { text: Math.round(brightness.value) + "%"; color: root.fg; font.pixelSize: 12; Layout.preferredWidth: 36 }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: daemon.connected
                      ? "cryod · " + daemon.profile + " profile"
                      : "cryod unreachable — is the service running?  sudo systemctl start cryod"
                color: root.muted
                font.pixelSize: 10
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}
