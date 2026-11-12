import QtQuick
import QtQuick.Effects

// The header brand mark: the frost crystal with its bloom.
Item {
    implicitWidth: 42
    implicitHeight: 42
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
        // static bloom - rendered once
        source: brandMark
        anchors.fill: brandMark
        shadowEnabled: true
        shadowColor: Theme.accent
        shadowOpacity: 0.55 * Theme.glow
        shadowBlur: 0.8
        blurMax: 20
    }
}
