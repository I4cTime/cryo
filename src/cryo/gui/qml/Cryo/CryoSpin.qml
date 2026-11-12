import QtQuick
import QtQuick.Controls.Basic

SpinBox {
    id: spin
    editable: true
    font.pixelSize: 12
    font.features: { "tnum": 1 }
    implicitWidth: 92
    implicitHeight: 28
    contentItem: TextInput {
        text: spin.textFromValue(spin.value, spin.locale)
        font: spin.font
        color: Theme.fg
        horizontalAlignment: Qt.AlignHCenter
        verticalAlignment: Qt.AlignVCenter
        readOnly: !spin.editable
        validator: spin.validator
        inputMethodHints: Qt.ImhFormattedNumbersOnly
        selectByMouse: true
    }
    background: Rectangle {
        color: Theme.track
        border.color: spin.activeFocus ? Theme.accent : Theme.panelBorder
        radius: 6
    }
    up.indicator: Rectangle {
        x: spin.width - width; height: spin.height; width: 22
        color: "transparent"
        Label { anchors.centerIn: parent; text: "+"; color: Theme.muted; font.pixelSize: 14 }
    }
    down.indicator: Rectangle {
        x: 0; height: spin.height; width: 22
        color: "transparent"
        Label { anchors.centerIn: parent; text: "−"; color: Theme.muted; font.pixelSize: 14 }
    }
}
