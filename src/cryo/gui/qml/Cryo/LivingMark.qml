import QtQuick
import QtQuick.Effects

// The header brand mark: the frost crystal with its bloom, and five frost
// motes orbiting it on three tilted ellipses, passing behind and in front.
// The orbit speed follows the fastest fan (about 0.12 rev/s at a standstill,
// 1 rev/s from 5000 rpm), easing so it never jumps. Dormant (cryod gone, no
// thermals) the motes fade out and the mark goes grey and dim without bloom.
// While Thermal Guard holds, the motes turn to ice.
//
// Cost: one FrameAnimation moving five plain rectangles, only while the
// window is live, motion is allowed and the mark is awake. Under reduce
// motion the motes sit at fixed positions.
Item {
    id: mark
    objectName: "livingMark"
    implicitWidth: 42
    implicitHeight: 42

    readonly property bool asleep: Ambient.dormant || !Ambient.connected
    // 1 awake, 0 asleep (eased when motion is allowed)
    property real awake: asleep ? 0 : 1
    Behavior on awake {
        enabled: Ambient.motion
        NumberAnimation { duration: 700; easing.type: Easing.InOutSine }
    }

    // ---- orbit speed ----
    readonly property int fastestRpm: {
        let m = 0
        for (const f of daemon.fans)
            m = Math.max(m, f.rpm)
        return m
    }
    readonly property real minSpeed: 0.12    // rev/s with the fans stopped
    readonly property real maxSpeed: 1.0     // rev/s from fullRpm up
    readonly property real fullRpm: 5000
    readonly property real targetSpeed: {
        const f = Math.max(0, Math.min(1, fastestRpm / fullRpm))
        // smoothstep: gentle at both ends of the range
        return minSpeed + (maxSpeed - minSpeed) * f * f * (3 - 2 * f)
    }
    property real speed: minSpeed            // eased toward targetSpeed per frame
    property real phase: 0                   // revolutions of the base orbit

    FrameAnimation {
        objectName: "markOrbit"
        running: Ambient.motion && mark.visible && mark.awake > 0
        onTriggered: {
            const dt = Math.min(frameTime, 0.1)
            mark.speed += (mark.targetSpeed - mark.speed) * Math.min(1, dt * 1.2)
            mark.phase = (mark.phase + mark.speed * dt) % 1000
        }
    }
    // Reduce motion parks the motes where they start.
    Connections {
        target: Prefs
        function onReduceMotionChanged() {
            if (Prefs.reduceMotion) {
                mark.phase = 0
                mark.speed = mark.targetSpeed
            }
        }
    }

    // ---- the crystal ----
    Image {
        // Frost-crystal brand mark. PNG rather than the SVG:
        // Qt's SVG renderer ignores the mark's blur filters, so
        // the pre-rendered raster carries the neon glow.
        id: brandMark
        anchors.fill: parent
        source: "../../assets/cryo-256.png"
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        visible: false
    }
    MultiEffect {
        // static bloom - rendered once; asleep it is grey, dim and bare
        source: brandMark
        anchors.fill: brandMark
        opacity: 0.42 + 0.58 * mark.awake
        saturation: -(1 - mark.awake)
        shadowEnabled: true
        shadowColor: Theme.accent
        shadowOpacity: 0.55 * Theme.glow * mark.awake
        shadowBlur: 0.8
        blurMax: 20
    }

    // ---- motes ----
    // Orbits: radius, tilt out of the screen plane (deg), in-plane rotation
    // (deg), relative speed. Each mote rides one orbit at a phase offset.
    readonly property var orbits: [
        { r: 19.5, tilt: 70, rot: -24, k: 1.0 },
        { r: 18.0, tilt: 74, rot: 38, k: 0.82 },
        { r: 21.0, tilt: 64, rot: 92, k: 1.17 }
    ]
    readonly property var motes: [
        { orbit: 0, at: 0.00, size: 3.0, ice: false },
        { orbit: 0, at: 0.50, size: 2.4, ice: true },
        { orbit: 1, at: 0.22, size: 2.6, ice: false },
        { orbit: 1, at: 0.72, size: 2.2, ice: true },
        { orbit: 2, at: 0.40, size: 2.8, ice: false }
    ]
    // Ice ink: the guard's frost white (a light style needs it darker to
    // read on its pale background).
    readonly property color iceInk: Theme.isLight ? Theme.frostShade : Theme.frostRim

    Repeater {
        model: mark.motes
        delegate: Item {
            id: mote
            required property var modelData
            readonly property var orbit: mark.orbits[modelData.orbit]
            readonly property real theta: 2 * Math.PI * (mark.phase * orbit.k + modelData.at)
            // circle in a tilted plane, projected, then turned in the screen plane
            readonly property real ox: orbit.r * Math.cos(theta)
            readonly property real oy: orbit.r * Math.sin(theta) * Math.cos(orbit.tilt * Math.PI / 180)
            readonly property real depth: Math.sin(theta)        // +1 nearest, -1 farthest
            readonly property real rot: orbit.rot * Math.PI / 180
            readonly property color ink: Ambient.guard ? mark.iceInk
                                         : modelData.ice ? Theme.mix(Theme.accent, mark.iceInk, 0.55)
                                         : Theme.accent
            width: 10
            height: 10
            x: mark.width / 2 + ox * Math.cos(rot) - oy * Math.sin(rot) - width / 2
            y: mark.height / 2 + ox * Math.sin(rot) + oy * Math.cos(rot) - height / 2
            z: depth >= 0 ? 1 : -1
            scale: 0.8 + 0.3 * depth
            opacity: mark.awake * (0.5 + 0.5 * (depth + 1) / 2)
            visible: opacity > 0.01

            Rectangle {      // outer glow
                anchors.centerIn: parent
                width: mote.modelData.size * 3.4
                height: width
                radius: width / 2
                color: Qt.alpha(mote.ink, 0.16 * Theme.glow + 0.06)
            }
            Rectangle {      // inner glow
                anchors.centerIn: parent
                width: mote.modelData.size * 1.9
                height: width
                radius: width / 2
                color: Qt.alpha(mote.ink, 0.38)
            }
            Rectangle {      // core
                anchors.centerIn: parent
                width: mote.modelData.size
                height: width
                radius: width / 2
                color: Theme.isLight ? mote.ink : Theme.mix(mote.ink, Theme.frostRim, 0.45)
            }
        }
    }
}
