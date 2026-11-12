import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Cryo

// The window: backdrop, window frost, then one scrolling column (home) or
// the Settings view above both. Look tokens live in
// Cryo/Theme.qml, runtime state in Cryo/Ambient.qml, preferences in
// Cryo/Prefs.qml, every piece of UI in its own file under Cryo/.
ApplicationWindow {
    id: root
    visible: true
    width: 480
    height: 860
    minimumWidth: 440
    title: (daemon.modelName ? "Cryo - " + daemon.modelName : "Cryo")
           + (daemon.demo ? " (demo)" : "")
    color: Theme.bg
    // Controls (and every Label) inherit the window font; Outfit is the UI
    // face, JetBrains Mono / tabular figures keep live numbers from jittering.
    font.family: Theme.uiFont

    // "home" (the control column) or "settings".
    property string page: "home"

    // Every looping animation (fan glyphs, badge pulses, lighting preview)
    // runs only while the window is on screen and focused: closed to the
    // tray, minimized or sitting unfocused, they freeze in place and the GUI
    // costs no more than its 1 Hz telemetry repaints.
    readonly property bool live: root.visible
                                 && root.active
                                 && root.visibility !== Window.Minimized
                                 && root.visibility !== Window.Hidden
    Binding { target: Ambient; property: "live"; value: root.live || Ambient.forceLive }
    Binding { target: Ambient; property: "connected"; value: daemon.connected }
    Binding { target: Ambient; property: "cpuTemp"; value: daemon.cpuTemp }
    Binding { target: Ambient; property: "gpuTemp"; value: daemon.gpuTemp }
    Binding { target: Ambient; property: "hasThermals"; value: daemon.hasThermals }
    Binding { target: Ambient; property: "guard"; value: daemon.connected && daemon.guard }
    Binding { target: Ambient; property: "profile"; value: daemon.profile }

    // Heat-driven washes (static when effects are off).
    Backdrop { id: backdrop; objectName: "backdrop" }
    Binding { target: Ambient; property: "backdrop"; value: backdrop }

    // Window frost, between the backdrop and the pages: every label, icon,
    // control and panel of both pages is drawn above it, so the ice never
    // covers anything to read or press. Its amount comes from Ambient (idle
    // frost by heat, the guard's flash freeze and thaw).
    //
    // The frost map runs past the window edge by this much, so the corner
    // ferns (which freeze first and reach furthest) start just outside the
    // pane. The Ambient amounts are tuned to these numbers (docs/THEME.md).
    readonly property real frostBleed: 28
    readonly property real frostBleedTop: 32
    readonly property real frostBleedBottom: 40

    FrostOverlay {
        id: frost
        objectName: "frost"
        anchors.fill: parent
        anchors.margins: -root.frostBleed
        anchors.topMargin: -root.frostBleedTop
        anchors.bottomMargin: -root.frostBleedBottom
        amount: Ambient.frostAmount
        tint: Theme.frost
        rimColor: Theme.frostRim
        intensity: Theme.frostIntensity
        shade: Theme.frostShade
        shadeStrength: Theme.frostShadeStrength
    }
    // Reduce motion (or an unfocused window) skips the sweep: the frost jumps
    // to its new amount and, if the window is live, crossfades from the old
    // one through this ghost for a moment. Hidden the rest of the time.
    FrostOverlay {
        id: frostGhost
        objectName: "frostGhost"
        anchors.fill: parent
        anchors.margins: -root.frostBleed
        anchors.topMargin: -root.frostBleedTop
        anchors.bottomMargin: -root.frostBleedBottom
        opacity: 0
        visible: opacity > 0 && amount > 0.001
        tint: Theme.frost
        rimColor: Theme.frostRim
        intensity: Theme.frostIntensity
        shade: Theme.frostShade
        shadeStrength: Theme.frostShadeStrength
    }

    // Sound cues for machine events (mode, guard, connection, errors).
    SoundWiring {}

    // Home and Settings crossfade (160 ms) when motion is allowed; with
    // reduce motion or an unfocused window the switch is instant.
    readonly property int pageFadeMs: 160

    Flickable {
        id: scroller
        objectName: "scroller"
        anchors.fill: parent
        opacity: root.page === "home" ? 1 : 0
        visible: opacity > 0
        Behavior on opacity {
            enabled: Ambient.motion
            NumberAnimation { duration: root.pageFadeMs; easing.type: Easing.OutCubic }
        }
        contentHeight: content.height + 40
        clip: true

        ColumnLayout {
            id: content
            x: 20
            y: 20
            width: root.width - 40
            spacing: 18

            Header {
                id: homeHeader
                onSettingsClicked: root.page = root.page === "home" ? "settings" : "home"
            }
            ErrorBanner {}
            PowerModes { objectName: "secModes" }
            Telemetry { objectName: "secTelemetry" }
            FanControl { objectName: "secFans" }
            CpuPower { objectName: "secCpu" }
            Automation { objectName: "secAutomation" }
            Lighting { objectName: "secLighting" }
            Footer {}
        }
    }

    Loader {
        id: settingsLoader
        objectName: "settingsLoader"
        anchors.fill: parent
        // Stays loaded until it has faded out.
        active: root.page === "settings" || opacity > 0
        opacity: root.page === "settings" ? 1 : 0
        visible: opacity > 0
        focus: root.page === "settings"
        Behavior on opacity {
            enabled: Ambient.motion
            NumberAnimation { duration: root.pageFadeMs; easing.type: Easing.OutCubic }
        }
        sourceComponent: SettingsPage { onBack: root.page = "home" }
        onLoaded: item.forceActiveFocus()
    }

    ParallelAnimation {
        id: frostCrossfade
        NumberAnimation { target: frostGhost; property: "opacity"; from: 1; to: 0; duration: 280 }
        NumberAnimation { target: frost; property: "opacity"; from: 0; to: 1; duration: 280 }
    }
    Connections {
        target: Ambient
        function onFrostJumped(from) {
            if (!Ambient.live)
                return
            frostGhost.amount = from
            frostCrossfade.restart()
        }
    }
}
