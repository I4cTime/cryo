import QtQuick

// Window frost. Lay it over the whole window content, above everything,
// and animate `amount`: 0 is a clear pane, about 0.4 frosts the outer band
// (corners first), 1 frosts the whole window. No timers or animation live
// in here, so at rest it costs nothing, and at amount 0 it is not drawn.
// It holds no input handlers, so clicks fall through to the content below.
Item {
    id: root

    property real amount: 0
    property real intensity: 0.9
    property color tint: "#BFEFFF"
    property color rimColor: "#FFFFFF"
    property real rimWidth: 0.03
    property real rimStrength: 0.9
    property real feather: 0.025
    property color shade: "#4A6478"
    property real shadeStrength: 0
    // A rect in this item's coordinates the frost keeps clear of (the
    // header controls), and how far the frost takes to return around it.
    // An empty rect clears nothing. Shader path only.
    property rect clearRect: Qt.rect(0, 0, 0, 0)
    property real clearFeather: 18

    // False on the software renderer, where ShaderEffect cannot run and a
    // pre-baked frost image (fixed shape, fading with amount) stands in.
    readonly property bool available: GraphicsInfo.api !== GraphicsInfo.Software

    enabled: false
    visible: amount > 0.001

    Image {
        id: growthMap
        visible: false
        smooth: true
        mipmap: false
        // Loaded only when the shader path is in use, and only here.
        source: root.available ? Qt.resolvedUrl("frost_growth.png") : ""
    }

    ShaderEffect {
        anchors.fill: parent
        visible: root.available
        blending: true

        readonly property var growth: growthMap
        readonly property real amount: Math.max(0, Math.min(1, root.amount))
        readonly property real intensity: root.intensity
        readonly property real feather: root.feather
        readonly property real rimWidth: root.rimWidth
        readonly property real rimStrength: root.rimStrength
        readonly property real shadeStrength: root.shadeStrength
        readonly property color tint: root.tint
        readonly property color rimColor: root.rimColor
        readonly property color shade: root.shade
        readonly property var clearRect: root.clearRect.width > 0 && root.clearRect.height > 0
            ? Qt.vector4d(root.clearRect.x, root.clearRect.y,
                          root.clearRect.x + root.clearRect.width, root.clearRect.y + root.clearRect.height)
            : Qt.vector4d(-1e5, -1e5, -1e5, -1e5)
        readonly property size size: Qt.size(width, height)
        readonly property real clearFeather: root.clearFeather

        fragmentShader: Qt.resolvedUrl("frost.frag.qsb")
    }

    Image {
        anchors.fill: parent
        visible: !root.available
        source: root.available ? "" : Qt.resolvedUrl("frost_static.png")
        smooth: true
        fillMode: Image.Stretch
        opacity: Math.min(1, root.amount / 0.4) * root.intensity / 0.9
    }
}
