import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Slider {
    id: control
    from: 0; to: 100; stepSize: 1
    Layout.fillWidth: true
    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: 5
        radius: 3
        color: Theme.track
        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 3
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Theme.accent2 }
                GradientStop { position: 1.0; color: Theme.accent }
            }
        }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: 16; height: 16; radius: 8
        color: Theme.fg
        border.color: Theme.accent
        border.width: 2
    }
}
