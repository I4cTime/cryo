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

    component CryoSpin: SpinBox {
        id: spin
        editable: true
        font.pixelSize: 12
        implicitWidth: 92
        implicitHeight: 28
        contentItem: TextInput {
            text: spin.textFromValue(spin.value, spin.locale)
            font: spin.font
            color: root.fg
            horizontalAlignment: Qt.AlignHCenter
            verticalAlignment: Qt.AlignVCenter
            readOnly: !spin.editable
            validator: spin.validator
            inputMethodHints: Qt.ImhFormattedNumbersOnly
            selectByMouse: true
        }
        background: Rectangle {
            color: "#141A26"
            border.color: spin.activeFocus ? root.cyan : root.panelBorder
            radius: 6
        }
        up.indicator: Rectangle {
            x: spin.width - width; height: spin.height; width: 22
            color: "transparent"
            Text { anchors.centerIn: parent; text: "+"; color: root.muted; font.pixelSize: 14 }
        }
        down.indicator: Rectangle {
            x: 0; height: spin.height; width: 22
            color: "transparent"
            Text { anchors.centerIn: parent; text: "−"; color: root.muted; font.pixelSize: 14 }
        }
    }

    component CryoButton: Rectangle {
        id: btn
        property string label
        property bool accent: false
        signal clicked()
        implicitHeight: 28
        implicitWidth: btnText.implicitWidth + 24
        radius: 6
        color: accent ? Qt.alpha(root.cyan, 0.15) : "#141A26"
        border.color: accent ? root.cyan : root.panelBorder
        opacity: enabled ? 1.0 : 0.4
        Text {
            id: btnText
            anchors.centerIn: parent
            text: btn.label
            color: btn.accent ? root.cyan : root.fg
            font.pixelSize: 12
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: btn.clicked()
        }
    }

    // One fan group's [temp, boost] points, edited locally and applied as
    // a whole so the daemon validates the curve in one go.
    component CurveEditor: ColumnLayout {
        id: editor
        property string group
        property var source: []           // daemon's current points
        property bool dirty: false
        spacing: 4
        Layout.fillWidth: true

        ListModel { id: points }

        function load() {
            points.clear()
            for (const p of editor.source)
                points.append({ temp: p[0], boost: p[1] })
            editor.dirty = false
        }
        onSourceChanged: if (!editor.dirty) load()
        Component.onCompleted: load()

        RowLayout {
            Layout.fillWidth: true
            Text { text: editor.group.toUpperCase() + " curve"; color: root.fg; font.pixelSize: 12; font.bold: true }
            Item { Layout.fillWidth: true }
            Text { text: "°C → boost %"; color: root.muted; font.pixelSize: 11 }
        }

        // The curve as a chart: temperature 30-110 °C across, boost 0-100 %
        // up, the daemon's live temperature as a marker. Repaints whenever
        // a point is edited so the numbers below and the line agree.
        Canvas {
            id: chart
            Layout.fillWidth: true
            Layout.preferredHeight: 120
            readonly property real tLo: 30
            readonly property real tHi: 110
            readonly property real liveTemp: editor.group === "gpu" ? daemon.gpuTemp : daemon.cpuTemp
            function px(t) { return 28 + (Math.min(Math.max(t, tLo), tHi) - tLo) / (tHi - tLo) * (width - 36) }
            function py(b) { return 8 + (1 - Math.min(Math.max(b, 0), 100) / 100) * (height - 26) }
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                // grid
                ctx.strokeStyle = "#141A26"; ctx.lineWidth = 1
                ctx.fillStyle = root.muted; ctx.font = "9px sans-serif"
                for (const b of [0, 50, 100]) {
                    ctx.beginPath(); ctx.moveTo(px(tLo), py(b)); ctx.lineTo(px(tHi), py(b)); ctx.stroke()
                    ctx.fillText(b + "%", 2, py(b) + 3)
                }
                for (const t of [40, 60, 80, 100]) {
                    ctx.beginPath(); ctx.moveTo(px(t), py(0)); ctx.lineTo(px(t), py(100)); ctx.stroke()
                    ctx.fillText(t + "°", px(t) - 8, height - 4)
                }
                // curve
                if (points.count === 0) return
                ctx.strokeStyle = root.cyan; ctx.lineWidth = 2
                ctx.beginPath()
                const first = points.get(0), last = points.get(points.count - 1)
                ctx.moveTo(px(tLo), py(first.boost))
                for (let i = 0; i < points.count; i++) {
                    const p = points.get(i)
                    ctx.lineTo(px(p.temp), py(p.boost))
                }
                ctx.lineTo(px(tHi), py(last.boost))
                ctx.stroke()
                // fill under the curve
                ctx.lineTo(px(tHi), py(0)); ctx.lineTo(px(tLo), py(0)); ctx.closePath()
                ctx.fillStyle = Qt.alpha(root.cyan, 0.08); ctx.fill()
                // points
                for (let i = 0; i < points.count; i++) {
                    const p = points.get(i)
                    ctx.beginPath(); ctx.arc(px(p.temp), py(p.boost), 4, 0, Math.PI * 2)
                    ctx.fillStyle = root.fg; ctx.fill()
                    ctx.strokeStyle = root.cyan; ctx.lineWidth = 2; ctx.stroke()
                }
                // Thermal Guard trip for this group: the fans go to 100% past
                // this line in every mode, whatever the curve says.
                const trip = editor.group === "gpu" ? daemon.guardGpuTrip : daemon.guardCpuTrip
                if (trip > tLo && trip < tHi) {
                    ctx.strokeStyle = "#FFB300"; ctx.lineWidth = 1
                    ctx.setLineDash([2, 4])
                    ctx.beginPath(); ctx.moveTo(px(trip), py(0)); ctx.lineTo(px(trip), py(100)); ctx.stroke()
                    ctx.setLineDash([])
                    ctx.fillStyle = "#FFB300"
                    ctx.fillText("guard " + trip + "°", px(trip) - 44, py(100) + 9)
                }
                // live temperature marker
                if (liveTemp > 0) {
                    ctx.strokeStyle = "#FF5470"; ctx.lineWidth = 1
                    ctx.setLineDash([3, 3])
                    ctx.beginPath(); ctx.moveTo(px(liveTemp), py(0)); ctx.lineTo(px(liveTemp), py(100)); ctx.stroke()
                    ctx.setLineDash([])
                    ctx.fillStyle = "#FF5470"
                    ctx.fillText(liveTemp.toFixed(0) + "°", px(liveTemp) + 3, py(100) + 9)
                }
            }
            Connections {
                target: points
                function onDataChanged() { chart.requestPaint() }
                function onRowsInserted() { chart.requestPaint() }
                function onRowsRemoved() { chart.requestPaint() }
                function onModelReset() { chart.requestPaint() }
            }
            Connections {
                target: daemon
                function onTelemetryChanged() { chart.requestPaint() }
                function onConfigChanged() { chart.requestPaint() }
            }
        }
        Repeater {
            model: points
            delegate: RowLayout {
                required property int index
                required property int temp
                required property int boost
                Layout.fillWidth: true
                spacing: 6
                CryoSpin {
                    from: 0; to: 110; value: temp
                    onValueModified: { points.setProperty(index, "temp", value); editor.dirty = true }
                }
                Text { text: "→"; color: root.muted; font.pixelSize: 12 }
                CryoSpin {
                    from: 0; to: 100; value: boost
                    onValueModified: { points.setProperty(index, "boost", value); editor.dirty = true }
                }
                Item { Layout.fillWidth: true }
                CryoButton {
                    label: "✕"
                    enabled: points.count > 2
                    onClicked: { points.remove(index); editor.dirty = true }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            CryoButton {
                label: "+ point"
                enabled: points.count < 8
                onClicked: {
                    const last = points.get(points.count - 1)
                    points.append({ temp: Math.min(110, last.temp + 5), boost: Math.min(100, last.boost + 10) })
                    editor.dirty = true
                }
            }
            CryoButton { label: "Revert"; enabled: editor.dirty; onClicked: editor.load() }
            Item { Layout.fillWidth: true }
            CryoButton {
                label: "Apply"
                accent: true
                enabled: editor.dirty
                onClicked: {
                    const out = []
                    for (let i = 0; i < points.count; i++) {
                        const p = points.get(i)
                        out.push([p.temp, p.boost])
                    }
                    daemon.setFanCurve(editor.group, out)
                    editor.dirty = false
                }
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
        objectName: "scroller"
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
            SectionTitle { text: "POWER MODES"; visible: daemon.hasProfiles }
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
            Panel {
                Layout.fillWidth: true
                visible: !daemon.hasThermals || !daemon.hasProfiles
                implicitHeight: limitedText.height + 24
                border.color: "#FFB300"
                Text {
                    id: limitedText
                    x: 14; y: 12
                    width: parent.width - 28
                    wrapMode: Text.WordWrap
                    color: "#FFB300"
                    font.pixelSize: 11
                    text: "Limited mode — the alienware-wmi driver doesn't expose "
                          + (!daemon.hasThermals && !daemon.hasProfiles ? "fans, temperatures or power modes"
                             : !daemon.hasThermals ? "fans or temperatures" : "power modes")
                          + " on this machine. Everything shown below still works. See cryoctl doctor."
                }
            }

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
            SectionTitle { text: "FAN CONTROL"; visible: daemon.hasThermals }
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
                        Column {
                            spacing: 2
                            Text { text: "Automatic fan curves"; color: root.fg; font.pixelSize: 13 }
                            Text { text: "Off = manual boost sliders"; color: root.muted; font.pixelSize: 11 }
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
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: !daemon.hasBoost
                                  ? "Fan boost is not supported by this model's firmware — curves and manual boost are unavailable."
                                  : daemon.profile === "custom"
                                  ? (curvesSwitch.checked
                                     ? "Curves active — boosts follow temperature."
                                     : "Manual boost — drag the sliders.")
                                  : "Fans follow the firmware in this mode. Custom mode hands them to Cryo."
                            color: daemon.hasBoost ? root.muted : "#FFB300"
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
                    Rectangle { Layout.fillWidth: true; height: 1; color: root.panelBorder; Layout.topMargin: 6; visible: daemon.hasBoost }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: daemon.hasBoost
                        Column {
                            spacing: 2
                            Text { text: "Curves & Thermal Guard"; color: root.fg; font.pixelSize: 13 }
                            Text {
                                text: curveBody.visible
                                      ? "Points are °C → boost %. Curves apply in Custom mode; the guard trips in any mode."
                                      : "Edit the curve points and the guard's trip temperatures."
                                color: root.muted
                                font.pixelSize: 11
                            }
                        }
                        Item { Layout.fillWidth: true }
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
                            Text { text: "Tuning & Thermal Guard"; color: root.fg; font.pixelSize: 12; font.bold: true }
                            GridLayout {
                                columns: 4
                                columnSpacing: 8
                                rowSpacing: 6
                                Layout.fillWidth: true
                                Text { text: "Hysteresis °C"; color: root.muted; font.pixelSize: 11 }
                                CryoSpin { id: hystSpin; from: 0; to: 15; onValueModified: tuning.dirty = true }
                                Text { text: "Min step %"; color: root.muted; font.pixelSize: 11 }
                                CryoSpin { id: stepSpin; from: 1; to: 25; onValueModified: tuning.dirty = true }
                                Text { text: "CPU trip °C"; color: root.muted; font.pixelSize: 11 }
                                CryoSpin { id: cpuTripSpin; from: 60; to: 105; onValueModified: tuning.dirty = true }
                                Text { text: "GPU trip °C"; color: root.muted; font.pixelSize: 11 }
                                CryoSpin { id: gpuTripSpin; from: 60; to: 105; onValueModified: tuning.dirty = true }
                                Text { text: "Release °C"; color: root.muted; font.pixelSize: 11 }
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

            // CPU power: turbo toggle + per-mode performance cap (0.4.0)
            SectionTitle { text: "CPU POWER"; visible: daemon.hasCpuCap || daemon.hasTurbo }
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
                        Column {
                            spacing: 2
                            Text { text: "Turbo Boost"; color: root.fg; font.pixelSize: 13 }
                            Text { text: "Off pins every core at its base clock — quiet and cool, slower."; color: root.muted; font.pixelSize: 11 }
                        }
                        Item { Layout.fillWidth: true }
                        CryoSwitch {
                            checked: daemon.turbo
                            Binding on checked { value: daemon.turbo }
                            onToggled: daemon.setTurbo(checked)
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: root.panelBorder; visible: daemon.hasTurbo && daemon.hasCpuCap; Layout.topMargin: 4; Layout.bottomMargin: 4 }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: daemon.hasCpuCap
                        Column {
                            spacing: 2
                            Text { text: "Performance cap per mode"; color: root.fg; font.pixelSize: 13 }
                            Text {
                                // Every configured mode at a glance, so you don't have
                                // to switch modes to see what each one is capped at.
                                property var caps: daemon.cpuCapProfiles
                                text: {
                                    const parts = []
                                    for (const name of daemon.profiles) {
                                        const pct = caps[name]
                                        if (pct !== undefined && pct < 100)
                                            parts.push((root.profileLabels[name] || name) + " " + pct + "%")
                                    }
                                    return parts.length ? parts.join("  ·  ") : "No mode is capped yet — pick a mode, then drag."
                                }
                                color: root.muted
                                font.pixelSize: 11
                            }
                        }
                        Item { Layout.fillWidth: true }
                        CryoSwitch {
                            id: capSwitch
                            checked: daemon.cpuCapEnabled
                            Binding on checked { value: daemon.cpuCapEnabled }
                            onToggled: daemon.setCpuCapEnabled(checked)
                        }
                    }
                    Text {
                        // Machine-specific: the GHz figure comes from this
                        // CPU's cpufreq max, never from a fixed model.
                        visible: daemon.hasCpuCap
                        text: "Caps the CPU's top performance state (intel_pstate max_perf_pct); remembered per mode, re-applied on every switch and after resume. "
                              + (daemon.cpuMaxMhz > 0
                                 ? "This CPU tops out at " + (daemon.cpuMaxMhz / 1000).toFixed(1) + " GHz; a lower cap trades a little single-core speed for less heat and power."
                                 : "A lower cap trades a little single-core speed for less heat and power.")
                        color: root.muted
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: daemon.hasCpuCap
                        enabled: capSwitch.checked
                        opacity: enabled ? 1.0 : 0.4
                        Text {
                            text: daemon.hasProfiles ? (root.profileLabels[daemon.profile] || daemon.profile) : "Default"
                            color: root.muted
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
                        Text {
                            text: Math.round(capSlider.value) + "%"
                                  + (daemon.cpuMaxMhz > 0
                                     ? "  ≈ " + (Math.round(capSlider.value) / 100 * daemon.cpuMaxMhz / 1000).toFixed(1) + " GHz"
                                     : "")
                            color: root.fg
                            font.pixelSize: 12
                            Layout.preferredWidth: 100
                        }
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
                                // From the daemon's config, not a fixed string.
                                property var rules: daemon.autoRules
                                function label(name) { return name ? (root.profileLabels[name] || name) : "—" }
                                text: (daemon.hasGameSense ? "game → " + label(rules.on_game) + " · " : "")
                                      + "battery → " + label(rules.on_battery)
                                      + " · AC → " + label(rules.on_ac)
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
                        spacing: 6
                        Text {
                            text: (daemon.ac ? "⚡ On AC power" : "🔋 On battery")
                                  + (daemon.gaming ? "  ·  🎮 game detected" : "")
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
