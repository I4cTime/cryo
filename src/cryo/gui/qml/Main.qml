import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes
import Cryo

// The window: backdrop, one scrolling column, one component per section.
// Look tokens live in Cryo/Theme.qml, runtime state in Cryo/Ambient.qml,
// every piece of UI in its own file under Cryo/.
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

    // Ambient backdrop: two faint neon washes at the top of the window.
    // Static - tessellated once per resize.
    Shape {
        anchors.fill: parent
        ShapePath {
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: root.width * 0.12; centerY: -40
                centerRadius: root.width * 0.95
                focalX: centerX; focalY: centerY
                GradientStop { position: 0.0; color: Qt.alpha(Theme.accent2, 0.16) }
                GradientStop { position: 1.0; color: "transparent" }
            }
            startX: 0; startY: 0
            PathLine { x: root.width; y: 0 }
            PathLine { x: root.width; y: root.height }
            PathLine { x: 0; y: root.height }
            PathLine { x: 0; y: 0 }
        }
        ShapePath {
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: root.width * 0.95; centerY: root.height * 0.35
                centerRadius: root.width * 0.8
                focalX: centerX; focalY: centerY
                GradientStop { position: 0.0; color: Qt.alpha(Theme.accent, 0.06) }
                GradientStop { position: 1.0; color: "transparent" }
            }
            startX: 0; startY: 0
            PathLine { x: root.width; y: 0 }
            PathLine { x: root.width; y: root.height }
            PathLine { x: 0; y: root.height }
            PathLine { x: 0; y: 0 }
        }
    }

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

            Header {}
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
}
