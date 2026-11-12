import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects

Rectangle {
    id: mode
    objectName: "mode-" + name
    property string name
    property string icon             // name in assets/icons
    property string label            // full name (tooltip)
    property string shortLabel       // fits a 1/7th-width cell
    readonly property bool active: daemon.profile === name
    // Equal-width cells: every mode shares one row, whatever its label.
    Layout.fillWidth: true
    Layout.preferredWidth: 1
    Layout.minimumWidth: 0
    Layout.preferredHeight: 56
    radius: 12

    // Hover: the border and the icon brighten (eased with motion).
    readonly property bool hovered: modeArea.containsMouse
    property real hoverT: hovered ? 1 : 0
    Behavior on hoverT { enabled: Ambient.motion; NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

    // Ice fill like a Panel; the active mode is tinted by the accent.
    property color fillTop: active ? Qt.alpha(Theme.accent, 0.14) : Theme.panelTop
    property color fillBottom: active ? Qt.alpha(Theme.accent, 0.07) : Theme.panel
    Behavior on fillTop { enabled: Ambient.motion; ColorAnimation { duration: 150 } }
    Behavior on fillBottom { enabled: Ambient.motion; ColorAnimation { duration: 150 } }
    gradient: Gradient {
        GradientStop { position: 0.0; color: mode.fillTop }
        GradientStop { position: 1.0; color: mode.fillBottom }
    }
    property color edge: active ? Theme.accent : Theme.mix(Theme.panelBorder, Theme.accent, 0.5 * hoverT)
    border.color: edge
    border.width: active ? 2 : 1
    Behavior on edge { enabled: Ambient.motion; ColorAnimation { duration: 150 } }

    // Neon tube: a blurred copy of the active border, inside and out.
    Rectangle {
        id: modeHaloSrc
        anchors.fill: parent
        radius: mode.radius
        color: "transparent"
        border.color: Theme.accent
        border.width: 2
        visible: false
    }
    MultiEffect {
        z: -1
        source: modeHaloSrc
        anchors.fill: modeHaloSrc
        opacity: mode.active ? 1 : 0
        visible: opacity > 0
        shadowEnabled: true
        shadowColor: Theme.accent
        shadowOpacity: Theme.glow
        shadowBlur: 0.9
        blurMax: 20
        Behavior on opacity { enabled: Ambient.motion; NumberAnimation { duration: 200 } }
    }

    // Frost bloom from the press point (nothing without motion).
    FrostBloom {
        id: bloom
        anchors.fill: parent
        radius: mode.radius
    }

    Column {
        anchors.centerIn: parent
        width: parent.width - 6
        spacing: 3
        Item {
            // Fixed box so the labels stay aligned under every icon.
            anchors.horizontalCenter: parent.horizontalCenter
            width: 20
            height: 20
            Icon {
                anchors.centerIn: parent
                name: mode.icon
                size: 18
                color: mode.active ? Theme.accent : Theme.muted
            }
            Icon {
                // the brightened icon, crossfaded in on hover (an icon's
                // colour is baked into its image, so it is not animated)
                anchors.centerIn: parent
                visible: opacity > 0
                opacity: mode.active ? 0 : mode.hoverT
                name: mode.icon
                size: 18
                color: Theme.mix(Theme.muted, Theme.fg, 0.8)
            }
        }
        Label {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: mode.shortLabel
            font.pixelSize: 10
            // Shrinks rather than clips if a cell gets narrower still.
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 8
            elide: Text.ElideRight
            font.weight: mode.active ? Font.Medium : Font.Normal
            color: mode.active ? Theme.fg : Theme.mix(Theme.muted, Theme.fg, 0.55 * mode.hoverT)
        }
    }
    MouseArea {
        id: modeArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onPressed: (mouse) => bloom.burst(mouse.x, mouse.y)
        onClicked: daemon.setProfile(mode.name)
    }
    ToolTip.visible: modeArea.containsMouse && mode.shortLabel !== mode.label
    ToolTip.delay: 400
    ToolTip.text: mode.label
}
