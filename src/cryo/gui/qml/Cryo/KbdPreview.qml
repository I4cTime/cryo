import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

// Stylized laptop keyboard previewing a lighting effect across four
// zones. Purely visual; the timings follow cryo/hw/effects.py so the
// preview moves like the chassis lights (rings, lid, power button).
// The real keyboard shows the effect's base colour (keyboard.py).
Item {
    id: kbd
    property string effect: "static"
    property color zoneColor: Theme.ledCyan
    property real level: 100             // brightness 0-100
    property real t: 0                   // effect clock, seconds
    // per-zone colour, left to right
    property color z0: Theme.ledOff
    property color z1: Theme.ledOff
    property color z2: Theme.ledOff
    property color z3: Theme.ledOff
    readonly property bool animated: ["quantum", "breathe", "spectrum", "rainbow", "wave", "backforth"]
                                     .indexOf(effect) >= 0
    // effects.RAINBOW
    readonly property var rainbow: [[1, 0, 0], [1, 0.647, 0], [1, 1, 0], [0, 0.502, 0],
                                    [0, 0.749, 1], [0, 0, 1], [0.502, 0, 0.502]]
    // One fixed size: the deck never stretches with the window (it is
    // a picture of a keyboard, not a layout), so key proportions and
    // the zone glow look the same at every window width. 372 is the
    // panel's inner width at the window's minimumWidth.
    implicitWidth: 372
    implicitHeight: deck.height

    function rgb(c) { return [c.r, c.g, c.b] }
    function lerp(a, b, f) { return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f] }
    function scaled(c, k) { return [c[0] * k, c[1] * k, c[2] * k] }
    // ELC morph actions: each step fades linearly from the previous
    // step's colour to its own over `dur` seconds, looping.
    function morph(seq, dur) {
        const n = seq.length
        const pos = kbd.t / dur
        const k = Math.floor(pos)
        return kbd.lerp(seq[((k - 1) % n + n) % n], seq[k % n], pos - k)
    }
    function zone(i) {
        const base = kbd.rgb(kbd.zoneColor), off = [0, 0, 0]
        switch (kbd.effect) {
        case "static":
            return base
        case "quantum":
            // the firmware's own colours, not the UI accent
            return kbd.morph([kbd.rgb(Theme.ledCyan), kbd.rgb(Theme.ledViolet)], 3)
        case "breathe": {
            // 0.5 s in, 2 s on, 0.5 s out, 2 s off
            const p = kbd.t % 5
            const f = p < 0.5 ? p / 0.5 : p < 2.5 ? 1 : p < 3 ? 1 - (p - 2.5) / 0.5 : 0
            return kbd.scaled(base, f)
        }
        case "spectrum":
            return kbd.morph(kbd.rainbow, 2)
        case "rainbow": {
            const seq = []
            for (let j = 0; j < kbd.rainbow.length; j++)
                seq.push(kbd.rainbow[(i + j) % kbd.rainbow.length])
            return kbd.morph(seq, 0.5)
        }
        case "wave":
        case "backforth": {
            // a lit zone stepping across (wave) or bouncing (backforth)
            const order = kbd.effect === "wave" ? [0, 1, 2, 3] : [0, 1, 2, 3, 2, 1]
            return kbd.morph(order.map(z => z === i ? base : off), 0.5)
        }
        default:
            return off
        }
    }
    function recompute() {
        const c = [zone(0), zone(1), zone(2), zone(3)]
        kbd.z0 = Qt.rgba(c[0][0], c[0][1], c[0][2], 1)
        kbd.z1 = Qt.rgba(c[1][0], c[1][1], c[1][2], 1)
        kbd.z2 = Qt.rgba(c[2][0], c[2][1], c[2][2], 1)
        kbd.z3 = Qt.rgba(c[3][0], c[3][1], c[3][2], 1)
    }
    onEffectChanged: { kbd.t = 0; recompute() }
    onZoneColorChanged: recompute()
    onTChanged: recompute()
    Component.onCompleted: recompute()

    FrameAnimation {
        objectName: "kbdAnim"
        running: Ambient.motion && kbd.visible && kbd.animated && kbd.level > 0
        onTriggered: kbd.t += Math.min(frameTime, 0.1)
    }

    // key rows in 1u widths, 15u per row
    readonly property var rows: [
        { h: 0.55, keys: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1] },
        { h: 1, keys: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2] },
        { h: 1, keys: [1.5, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1.5] },
        { h: 1, keys: [1.75, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2.25] },
        { h: 1, keys: [2.25, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2.75] },
        { h: 1, keys: [1.25, 1, 1, 1.25, 5, 1.25, 1.25, 1, 1, 1] }
    ]
    readonly property real gap: 3
    readonly property real rowH: 14
    readonly property real lit: Math.max(0, Math.min(1, kbd.level / 100))

    // Zone light spilling out around the deck: a blurred copy of the
    // zone gradient, rendered through a 64x24 texture so re-blurring it
    // every frame while an effect animates stays negligible.
    Rectangle {
        id: spillSrc
        anchors.fill: deck
        radius: deck.radius
        visible: false
        layer.enabled: true
        layer.textureSize: Qt.size(64, 24)
        layer.smooth: true
        gradient: zoneGradient
    }
    MultiEffect {
        source: spillSrc
        anchors.fill: spillSrc
        blurEnabled: true
        blur: 1.0
        blurMax: 32
        opacity: 0.8 * kbd.lit
        visible: kbd.lit > 0
    }
    Gradient {
        id: zoneGradient
        orientation: Gradient.Horizontal
        GradientStop { position: 0.00; color: kbd.z0 }
        GradientStop { position: 0.19; color: kbd.z0 }
        GradientStop { position: 0.31; color: kbd.z1 }
        GradientStop { position: 0.44; color: kbd.z1 }
        GradientStop { position: 0.56; color: kbd.z2 }
        GradientStop { position: 0.69; color: kbd.z2 }
        GradientStop { position: 0.81; color: kbd.z3 }
        GradientStop { position: 1.00; color: kbd.z3 }
    }

    Rectangle {
        id: deck
        width: kbd.implicitWidth
        height: keyArea.height + 22 + palm.height
        radius: 12
        color: Theme.deck
        border.color: Theme.deckEdge
        border.width: 1

        Item {
            id: keyArea
            x: 11
            y: 11
            width: parent.width - 22
            height: kbd.rowH * 5.55 + kbd.gap * 5

            // backlight: four zones blended at their seams
            Rectangle {
                anchors.fill: parent
                anchors.margins: -1
                radius: 4
                opacity: kbd.lit
                gradient: zoneGradient
            }
            Column {
                spacing: kbd.gap
                Repeater {
                    model: kbd.rows
                    delegate: Row {
                        id: keyRow
                        required property var modelData
                        readonly property real unit: (keyArea.width - kbd.gap * (modelData.keys.length - 1)) / 15
                        spacing: kbd.gap
                        Repeater {
                            model: keyRow.modelData.keys
                            delegate: Rectangle {
                                required property real modelData
                                width: modelData * keyRow.unit
                                height: kbd.rowH * keyRow.modelData.h
                                radius: 2.5
                                // translucent caps: the zone light glows
                                // through them and blazes in the gaps
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: Qt.alpha(Theme.keycap, 0.55) }
                                    GradientStop { position: 1.0; color: Qt.alpha(Theme.keycap, 0.86) }
                                }
                                border.color: Theme.keycapEdge
                                border.width: 1
                            }
                        }
                    }
                }
            }
        }
        Rectangle {
            id: palm
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 6
            width: parent.width * 0.3
            height: 20
            radius: 4
            color: "transparent"
            border.color: Theme.deckEdge
            border.width: 1
        }
    }
}
