import QtQuick
import QtQuick.Window

// One icon from src/cryo/gui/assets/icons, tinted by `color`, drawn by the
// cryoicon image provider (cryo/gui/icons.py) at exactly the device-pixel
// size it shows at, so it is crisp at fractional scale factors and needs no
// shader (works on the software renderer too).
Image {
    id: icon
    property string name
    property color color: Theme.fg
    property real size: 16
    // QML colours print as #RRGGBB or #AARRGGBB; the provider takes either.
    readonly property string colorHex: icon.color.toString().slice(1)
    readonly property real dpr: Screen.devicePixelRatio > 0 ? Screen.devicePixelRatio : 1
    width: size
    height: size
    sourceSize.width: Math.ceil(size * dpr)
    sourceSize.height: Math.ceil(size * dpr)
    fillMode: Image.PreserveAspectFit
    smooth: true
    source: name ? "image://cryoicon/" + name + "?color=" + colorHex : ""
}
