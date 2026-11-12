import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Effects

// Temperature ring gauge over a gradient sparkline of the session.
Panel {
    id: tile
    property string label
    property real temp
    property real peak: 0
    property int rpm
    property var history: []
    property color accent: Theme.accent
    // Eased copy of `temp`: the number and the arc glide to each reading.
    property real shown: temp
    Behavior on shown {
        enabled: Ambient.motion
        NumberAnimation { duration: 700; easing.type: Easing.OutCubic }
    }
    readonly property real lo: 30
    readonly property real hi: 100
    function frac(t) { return Math.min(Math.max((t - lo) / (hi - lo), 0), 1) }
    readonly property color arcColor: Theme.tempColor(shown)
    Layout.fillWidth: true
    Layout.preferredHeight: 128

    Canvas {
        id: spark
        anchors.fill: parent
        anchors.margins: 1
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const h = tile.history
            if (!h || h.length < 2)
                return
            // keep the fill inside the tile's rounded corners
            ctx.beginPath()
            ctx.roundedRect(0, 0, width, height, tile.radius - 1, tile.radius - 1)
            ctx.clip()
            // 30-100 °C mapped onto the lower part of the tile, under the readouts
            const band = height * 0.7
            const pts = []
            let top = height
            for (let i = 0; i < h.length; i++) {
                const x = i / (h.length - 1) * width
                const y = height - tile.frac(h[i]) * band
                pts.push([x, y])
                top = Math.min(top, y)
            }
            const fill = ctx.createLinearGradient(0, top, 0, height)
            fill.addColorStop(0, Qt.alpha(tile.accent, 0.22))
            fill.addColorStop(1, Qt.alpha(tile.accent, 0.0))
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
            ctx.strokeStyle = Qt.alpha(tile.accent, 0.8)
            ctx.lineWidth = 1.5
            ctx.lineJoin = "round"
            ctx.stroke()
        }
        Connections {
            target: daemon
            function onTelemetryChanged() { spark.requestPaint() }
        }
        Connections {
            target: Theme
            function onRevisionChanged() { spark.requestPaint() }
        }
    }

    Item {
        id: gauge
        width: 100
        height: 100
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        readonly property real stroke: 7
        readonly property real r: width / 2 - stroke / 2 - 1
        readonly property real start: 135     // 270° sweep, gap at the bottom
        readonly property real span: 270

        Rectangle {
            // gauge face: keeps the sparkline out from behind the number
            anchors.centerIn: parent
            width: 2 * gauge.r + gauge.stroke + 4
            height: width
            radius: width / 2
            color: Theme.panel
        }
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.track
                strokeWidth: gauge.stroke
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: gauge.width / 2; centerY: gauge.height / 2
                    radiusX: gauge.r; radiusY: gauge.r
                    startAngle: gauge.start; sweepAngle: gauge.span
                }
            }
        }
        Shape {
            id: arc
            anchors.fill: parent
            visible: false
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: tile.arcColor
                strokeWidth: gauge.stroke
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: gauge.width / 2; centerY: gauge.height / 2
                    radiusX: gauge.r; radiusY: gauge.r
                    startAngle: gauge.start
                    sweepAngle: Math.max(0.5, gauge.span * tile.frac(tile.shown))
                }
            }
        }
        MultiEffect {
            // the value arc plus its neon bloom
            source: arc
            anchors.fill: arc
            visible: tile.temp > 0
            shadowEnabled: true
            shadowColor: tile.arcColor
            shadowOpacity: 0.9 * Theme.glow
            shadowBlur: 0.7
            blurMax: 16
        }
        Item {
            // session peak: a small tick across the ring
            anchors.fill: parent
            visible: tile.peak > 0
            rotation: gauge.start + gauge.span * tile.frac(tile.peak)
            Rectangle {
                width: gauge.stroke + 7
                height: 2.5
                radius: 1
                x: gauge.width / 2 + gauge.r - width / 2
                y: gauge.height / 2 - height / 2
                antialiasing: true
                color: tile.peak >= 88 ? Theme.hot : Theme.fg
            }
        }
        Column {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: 2
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: tile.temp > 0 ? Math.round(tile.shown) : "-"
                color: tile.temp >= 85 ? Theme.hot : Theme.fg
                font.pixelSize: 28
                font.weight: Font.DemiBold
                font.features: { "tnum": 1 }
            }
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "°C"
                visible: tile.temp > 0
                color: Theme.muted
                font.pixelSize: 10
                font.letterSpacing: 1
            }
        }
    }

    ColumnLayout {
        anchors.left: gauge.right
        anchors.leftMargin: 12
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4
        RowLayout {
            Layout.fillWidth: true
            Label {
                Layout.fillWidth: true
                text: tile.label
                color: Theme.muted
                font.pixelSize: 11
                font.letterSpacing: 2
                font.bold: true
            }
            FanGlyph {
                rpm: tile.rpm
                animName: tile.label.toLowerCase() + "FanSpin"
                tint: tile.accent
            }
        }
        Mono {
            Layout.fillWidth: true
            Layout.topMargin: 2
            text: tile.rpm + " rpm"
            color: Theme.fg
            font.pixelSize: 11
            elide: Text.ElideRight
        }
        Mono {
            Layout.fillWidth: true
            visible: tile.peak > 0
            text: "peak " + tile.peak.toFixed(0) + "°"
            color: tile.peak >= 88 ? Theme.hot : Theme.muted
            font.pixelSize: 11
            elide: Text.ElideRight
        }
    }
}
