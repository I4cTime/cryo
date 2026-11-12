pragma Singleton
import QtQuick

// Runtime state every component may react to. A singleton cannot see the
// window or the `daemon` context property, so Main.qml pushes `live`,
// `connected`, the temperatures, `guard` and `profile` in with Bindings.
//
// Thermal chrome lives here: `heat` (how hot the machine is, 0..1) and
// `frostAmount` (what the window frost overlay shows, 0..1), including the
// Thermal Guard flash freeze. Nothing here animates continuously: heat moves
// in whole-degree steps at the telemetry cadence (1 Hz) and only eases on a
// big jump; the frost animates only for the guard sweep and the thaw.
QtObject {
    id: ambient

    // The window is on screen and focused (Main.qml computes it; when
    // forceLive is set it pushes true regardless).
    property bool live: false
    // Test hook: offscreen and headless windows are never focused, so the
    // tour and tests set this to see the app as a focused user does.
    property bool forceLive: false
    // Gate for every looping, sweeping or easing animation.
    readonly property bool motion: live && !Prefs.reduceMotion
    // cryod reachable (mirrors daemon.connected).
    property bool connected: false
    // cryod unreachable: the telemetry on screen is the last reading. The
    // temperature tiles, the dGPU load and VRAM dim to staleOpacity, their
    // arcs and figures go muted and the fan glyphs stop (capability
    // honesty: shown, never hidden). Controls are not affected.
    readonly property bool stale: !connected
    readonly property real staleOpacity: 0.45

    // ---- pushed from the daemon by Main.qml ----
    property real cpuTemp: 0
    property real gpuTemp: 0
    property bool hasThermals: true
    property bool guard: false          // Thermal Guard engaged (and connected)
    property string profile: ""
    // The window's Backdrop (Main.qml sets it): Clearing.qml asks it for
    // the ground colour under a label (Backdrop.colourAt).
    property Item backdrop: null

    // ---- heat ----
    // No temperatures to go by (disconnected, no thermals, no reading yet):
    // the chrome sits at a neutral heat and reads as dormant.
    readonly property bool dormant: !connected || !hasThermals || Math.max(cpuTemp, gpuTemp) <= 0
    readonly property real neutralHeat: 0.4
    readonly property real coldTemp: 45      // °C at heat 0
    readonly property real hotTemp: 85       // °C at heat 1
    // max(cpu, gpu) rounded to a whole degree, so sub-degree jitter never
    // repaints the window.
    readonly property real heatTarget: dormant
        ? neutralHeat
        : Math.max(0, Math.min(1, (Math.round(Math.max(cpuTemp, gpuTemp)) - coldTemp) / (hotTemp - coldTemp)))
    property real heat: neutralHeat
    readonly property real heatJump: 0.15    // bigger steps ease, smaller ones snap

    function _updateHeat() {
        heatEase.stop()
        if (motion && Math.abs(heatTarget - heat) > heatJump) {
            heatEase.from = heat
            heatEase.to = heatTarget
            heatEase.start()
        } else {
            heat = heatTarget
        }
    }
    onHeatTargetChanged: _updateHeat()
    readonly property NumberAnimation heatEase: NumberAnimation {
        target: ambient; property: "heat"; duration: 400; easing.type: Easing.OutCubic
    }

    // ---- frost ----
    // Idle frost frames the window while cool and is gone by about 69 °C.
    readonly property real idleMax: 0.48
    readonly property real idleFade: 0.6     // heat at which idle frost is gone
    readonly property real peakAmount: 1.0  // flash freeze overshoot
    readonly property real heldAmount: 0.6  // frosted frame while the guard holds
    // Dormant (no daemon, no thermals) the window looks iced over and
    // asleep: a light fixed frost instead of the heat-derived one. The
    // switch eases over 600 ms when motion is allowed.
    readonly property real dormantFrost: 0.42
    property real dormantMix: 0              // 0 awake .. 1 dormant
    onDormantChanged: {
        dormantEase.stop()
        if (motion) {
            dormantEase.to = dormant ? 1 : 0
            dormantEase.start()
        } else {
            dormantMix = dormant ? 1 : 0
        }
    }
    readonly property NumberAnimation dormantEase: NumberAnimation {
        target: ambient; property: "dormantMix"; duration: 600; easing.type: Easing.InOutSine
    }
    readonly property real heatFrost: idleMax * Math.max(0, Math.min(1, 1 - heat / idleFade))
    readonly property real idleFrost: heatFrost + (dormantFrost - heatFrost) * dormantMix
    // "none", "sweep" (freezing over), "held" (settled, guard on), "thaw".
    property string guardPhase: "none"
    property real guardFrost: 0
    // The thaw blends from the frost the guard left (guardFrost at release)
    // to the LIVE idle target, so a target that moves meanwhile (temps
    // falling, a disconnect turning dormant) is followed and the end of the
    // thaw meets idleFrost exactly: no jump when the phase returns to "none".
    property real thawProgress: 0            // 0 at release .. 1 thawed
    readonly property real thawFrost: guardFrost + (idleFrost - guardFrost) * thawProgress
    readonly property real frostAmount: !Prefs.effects ? 0
                                        : guardPhase === "none" ? idleFrost
                                        : guardPhase === "thaw" ? thawFrost : guardFrost
    // Panel edges ice over with the flash freeze (Panel.qml): 0 clear, 1
    // iced. It rises with the sweep, holds while the guard holds and thaws
    // with the frost, from wherever it stood, so it never steps; without
    // motion the phases jump, and so does this.
    property real _sweepFrom: 0      // frostAmount when the sweep started
    property real _edgeFrom: 0       // edgeIce then
    property real _edgeAtRelease: 0  // edgeIce when the thaw started
    readonly property real _sweepIce: {
        const k = Math.max(0, Math.min(1, (guardFrost - _sweepFrom) / Math.max(1e-6, peakAmount - _sweepFrom)))
        return _edgeFrom + (1 - _edgeFrom) * k
    }
    readonly property real edgeIce: !Prefs.effects ? 0
                                    : guardPhase === "sweep" ? _sweepIce
                                    : guardPhase === "held" ? 1
                                    : guardPhase === "thaw" ? _edgeAtRelease * (1 - thawProgress) : 0
    // The frost jumped without a sweep (reduce motion or unfocused): the
    // overlay crossfades from the previous amount if the window is live.
    signal frostJumped(real from)

    onGuardChanged: guard ? _engage() : _release()
    function _engage() {
        thawAnim.stop()
        const from = frostAmount
        if (!motion || !Prefs.effects) {
            guardFrost = heldAmount
            guardPhase = "held"
            if (Prefs.effects)
                frostJumped(from)
            return
        }
        _edgeFrom = edgeIce
        _sweepFrom = from
        guardFrost = from
        guardPhase = "sweep"
        sweepAnim.start()
    }
    function _release() {
        sweepAnim.stop()
        if (guardPhase === "none")
            return
        const from = frostAmount
        if (!motion || !Prefs.effects) {
            guardPhase = "none"
            if (Prefs.effects)
                frostJumped(from)
            return
        }
        // guardFrost holds where the sweep or hold stopped; the blend starts
        // there (progress 0 before the phase flips, so nothing steps).
        thawProgress = 0
        _edgeAtRelease = edgeIce
        guardPhase = "thaw"
        thawAnim.restart()
    }
    readonly property SequentialAnimation sweepAnim: SequentialAnimation {
        NumberAnimation {
            target: ambient; property: "guardFrost"; to: ambient.peakAmount
            duration: 550; easing.type: Easing.OutCubic
        }
        ScriptAction { script: ambient.guardPhase = "held" }
        NumberAnimation {
            target: ambient; property: "guardFrost"; to: ambient.heldAmount
            duration: 800; easing.type: Easing.InOutSine
        }
    }
    readonly property NumberAnimation thawAnim: NumberAnimation {
        target: ambient; property: "thawProgress"; from: 0; to: 1
        duration: 2500; easing.type: Easing.InOutSine
        onFinished: ambient.guardPhase = "none"
    }

    // ---- reveal: the sections crystallize in once, at first show ----
    // The first time the window is live, `reveal(animate)` goes out (a beat
    // later, so every section is listening) and `revealed` turns true;
    // Crystallize.qml plays it per section. A window that never becomes
    // live soon (started hidden in the tray, or shown unfocused) skips it:
    // after `revealDeadline` the sections simply show.
    property bool revealed: false
    signal reveal(bool animate)
    function _reveal() {
        if (revealed)
            return
        reveal(motion)
        if (motion)
            revealShadowAnim.restart()
        revealed = true
    }
    // Panel drop shadows settle in at the end of the reveal: under a
    // half-faded panel the shadow (and the fill it is cast from) would show
    // through (grey slabs on a light style).
    property real revealShadow: 1
    readonly property NumberAnimation revealShadowAnim: NumberAnimation {
        target: ambient; property: "revealShadow"; from: 0; to: 1
        duration: 900; easing.type: Easing.InCubic
    }
    onLiveChanged: {
        if (live && !revealed)
            revealKick.restart()
        if (!live && revealShadowAnim.running) {     // never animate unseen
            revealShadowAnim.stop()
            revealShadow = 1
        }
    }
    readonly property Timer revealKick: Timer { interval: 40; onTriggered: ambient._reveal() }
    readonly property Timer revealDeadline: Timer {
        interval: 1500; running: !ambient.revealed
        onTriggered: if (!ambient.revealed) { ambient.reveal(false); ambient.revealed = true }
    }
    // Tour hook: play the reveal again (needs a live window).
    function replayReveal() {
        revealed = false
        _reveal()
    }

    // Jump every running chrome animation to where it is heading (the tour
    // calls this between scenes so each shot starts from rest).
    function snap() {
        heatEase.stop()
        heat = heatTarget
        dormantEase.stop()
        dormantMix = dormant ? 1 : 0
        sweepAnim.stop()
        thawAnim.stop()
        thawProgress = 0
        guardFrost = guard ? heldAmount : 0
        guardPhase = guard ? "held" : "none"
    }

    Component.onCompleted: {
        heat = heatTarget
        dormantMix = dormant ? 1 : 0
    }
}
