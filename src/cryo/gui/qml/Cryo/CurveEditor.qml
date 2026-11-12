import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// One fan group's [temp, boost] points, edited locally and applied as
// a whole so the daemon validates the curve in one go.
ColumnLayout {
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
        Label { text: editor.group.toUpperCase() + " curve"; color: Theme.fg; font.pixelSize: 12; font.bold: true }
        Item { Layout.fillWidth: true }
        Label { text: "°C → boost %"; color: Theme.muted; font.pixelSize: 11 }
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
            ctx.strokeStyle = Theme.track; ctx.lineWidth = 1
            ctx.fillStyle = Theme.muted; ctx.font = "9px \"" + Theme.monoFont + "\""
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
            ctx.strokeStyle = Theme.accent; ctx.lineWidth = 2
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
            ctx.fillStyle = Qt.alpha(Theme.accent, 0.08); ctx.fill()
            // points
            for (let i = 0; i < points.count; i++) {
                const p = points.get(i)
                ctx.beginPath(); ctx.arc(px(p.temp), py(p.boost), 4, 0, Math.PI * 2)
                ctx.fillStyle = Theme.fg; ctx.fill()
                ctx.strokeStyle = Theme.accent; ctx.lineWidth = 2; ctx.stroke()
            }
            // Thermal Guard trip for this group: the fans go to 100% past
            // this line in every mode, whatever the curve says.
            const trip = editor.group === "gpu" ? daemon.guardGpuTrip : daemon.guardCpuTrip
            if (trip > tLo && trip < tHi) {
                ctx.strokeStyle = Theme.warn; ctx.lineWidth = 1
                ctx.setLineDash([2, 4])
                ctx.beginPath(); ctx.moveTo(px(trip), py(0)); ctx.lineTo(px(trip), py(100)); ctx.stroke()
                ctx.setLineDash([])
                ctx.fillStyle = Theme.warn
                ctx.fillText("guard " + trip + "°", px(trip) - 44, py(100) + 9)
            }
            // live temperature marker
            if (liveTemp > 0) {
                ctx.strokeStyle = Theme.hot; ctx.lineWidth = 1
                ctx.setLineDash([3, 3])
                ctx.beginPath(); ctx.moveTo(px(liveTemp), py(0)); ctx.lineTo(px(liveTemp), py(100)); ctx.stroke()
                ctx.setLineDash([])
                ctx.fillStyle = Theme.hot
                // The guard label sits just left of its line; drop the
                // live label a row when it would land on top of it.
                const dx = px(trip) - px(liveTemp)
                const clash = trip > tLo && trip < tHi && dx >= 0 && dx < 72
                ctx.fillText(liveTemp.toFixed(0) + "°", px(liveTemp) + 3, py(100) + (clash ? 21 : 9))
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
        Connections {
            target: Theme
            function onRevisionChanged() { chart.requestPaint() }
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
            Label { text: "→"; color: Theme.muted; font.pixelSize: 12 }
            CryoSpin {
                from: 0; to: 100; value: boost
                onValueModified: { points.setProperty(index, "boost", value); editor.dirty = true }
            }
            Item { Layout.fillWidth: true }
            CryoButton {
                icon: "close"
                tooltip: "Remove point"
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
