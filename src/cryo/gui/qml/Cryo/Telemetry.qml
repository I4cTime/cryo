import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Telemetry: limited-mode notice, temperature tiles, dGPU load, VRAM.
ColumnLayout {
    id: section
    Layout.fillWidth: true
    spacing: 18

    function fanRpm(group) {
        let total = 0, n = 0
        for (const f of daemon.fans)
            if (f.group === group) { total += f.rpm; n++ }
        return n ? Math.round(total / n) : 0
    }

    Panel {
        Layout.fillWidth: true
        visible: !daemon.hasThermals || !daemon.hasProfiles
        implicitHeight: limitedText.height + 24
        border.color: Theme.warn
        Label {
            id: limitedText
            x: 14; y: 12
            width: parent.width - 28
            wrapMode: Text.WordWrap
            color: Theme.warn
            font.pixelSize: 11
            text: "Limited mode - the alienware-wmi driver doesn't expose "
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
            rpm: section.fanRpm("cpu")
            history: daemon.cpuHistory
            accent: Theme.accent
        }
        StatTile {
            label: "GPU"
            temp: daemon.gpuTemp
            peak: daemon.gpuPeak
            rpm: section.fanRpm("gpu")
            history: daemon.gpuHistory
            accent: Theme.accent2Text
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Label { text: "dGPU load"; color: Theme.muted; font.pixelSize: 11 }
        Rectangle {
            Layout.fillWidth: true
            height: 5; radius: 3
            color: Theme.track
            Rectangle {
                width: parent.width * daemon.gpuUtil / 100
                height: parent.height; radius: 3
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.accent2 }
                    GradientStop { position: 1.0; color: Theme.accent2Text }
                }
                Behavior on width { enabled: Ambient.motion; NumberAnimation { duration: 300 } }
            }
        }
        Mono { text: daemon.gpuUtil + "%"; color: Theme.fg; font.pixelSize: 11 }
    }

    // VRAM - sparkline scaled to the card's full capacity, so a
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
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                const h = daemon.vramHistory
                if (!h || h.length < 2 || daemon.vramTotal <= 0)
                    return
                ctx.beginPath()
                ctx.roundedRect(0, 0, width, height, 11, 11)
                ctx.clip()
                const pts = []
                let top = height
                for (let i = 0; i < h.length; i++) {
                    const x = i / (h.length - 1) * width
                    const y = height - Math.min(h[i] / daemon.vramTotal, 1) * height
                    pts.push([x, y])
                    top = Math.min(top, y)
                }
                const fill = ctx.createLinearGradient(0, top, 0, height)
                fill.addColorStop(0, Qt.alpha(Theme.accent2Text, 0.14))
                fill.addColorStop(1, Qt.alpha(Theme.accent2Text, 0.0))
                ctx.beginPath()
                ctx.moveTo(0, height)
                for (const p of pts)
                    ctx.lineTo(p[0], p[1])
                ctx.lineTo(width, height)
                ctx.closePath()
                ctx.fillStyle = fill
                ctx.fill()
                ctx.beginPath()
                for (let i = 0; i < pts.length; i++)
                    i === 0 ? ctx.moveTo(pts[i][0], pts[i][1]) : ctx.lineTo(pts[i][0], pts[i][1])
                ctx.strokeStyle = Qt.alpha(Theme.accent2Text, 0.45)
                ctx.lineWidth = 1.5
                ctx.lineJoin = "round"
                ctx.stroke()
            }
            Connections {
                target: daemon
                function onTelemetryChanged() { vramSpark.requestPaint() }
            }
            Connections {
                target: Theme
                function onRevisionChanged() { vramSpark.requestPaint() }
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
                    Label { text: "VRAM"; color: Theme.muted; font.pixelSize: 11; font.letterSpacing: 1.5 }
                    Label {
                        text: (daemon.vramUsed / 1024).toFixed(1) + " GB"
                        font.features: { "tnum": 1 }
                        color: daemon.vramUsed / daemon.vramTotal >= 0.9 ? Theme.hot : Theme.fg
                        font.pixelSize: 20
                        font.bold: true
                    }
                }
                Item { Layout.fillWidth: true }
                Column {
                    spacing: 2
                    Mono {
                        anchors.right: parent.right
                        text: "peak " + (daemon.vramPeak / 1024).toFixed(1)
                              + " · of " + (daemon.vramTotal / 1024).toFixed(1) + " GB"
                        color: Theme.muted
                        font.pixelSize: 11
                    }
                    Mono {
                        anchors.right: parent.right
                        visible: daemon.gpuPower > 0
                        text: daemon.gpuPower.toFixed(0) + " W · "
                              + daemon.gpuClock + " MHz"
                        color: Theme.muted
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
                    Label {
                        text: modelData.name
                        color: Theme.muted
                        font.pixelSize: 10
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    Mono {
                        text: (modelData.vram_mb / 1024).toFixed(1) + " GB"
                        color: Theme.fg
                        font.pixelSize: 10
                    }
                }
            }
        }
    }
}
