import QtQuick

// One section's part of the first-show reveal: the section fades in and
// rises 8 px into place while a frost glint runs across its title, after a
// stagger of `order` x 60 ms. Ambient decides when (once, the first time the
// window is live) and whether it animates; under reduce motion, without a
// live window or on the software renderer it is an instant show.
//
// Not an Item, so it takes no slot in the section's layout. The section
// binds `opacity: reveal.t` and `transform: Translate { y: reveal.rise }`
// (never y: the layout must not move).
QtObject {
    id: c
    required property Item target       // the section (for the renderer check)
    property Item title                  // its SectionTitle, for the glint
    property int order: 0

    // 0 hidden .. 1 in place. Hidden from the start only while a reveal is
    // still to come; anything else shows at once.
    property real t: Ambient.revealed || Prefs.reduceMotion ? 1 : 0
    readonly property real rise: 8 * (1 - t)
    // glint position across the title, 0..1 (inactive outside)
    property real sweep: 0

    readonly property bool software: target !== null
                                     && target.GraphicsInfo.api === GraphicsInfo.Software

    function play(animate) {
        anim.stop()
        if (!animate || software) {
            t = 1
            sweep = 0
            return
        }
        t = 0
        sweep = 0
        anim.start()
    }
    readonly property Connections _reveal: Connections {
        target: Ambient
        function onReveal(animate) { c.play(animate) }
        // Losing the window mid-reveal lands it at once.
        function onLiveChanged() {
            if (!Ambient.live && c.anim.running)
                c.play(false)
        }
    }

    readonly property SequentialAnimation anim: SequentialAnimation {
        PauseAnimation { duration: 60 * c.order }
        ParallelAnimation {
            NumberAnimation {
                target: c; property: "t"; from: 0; to: 1
                duration: 460; easing.type: Easing.OutCubic
            }
            SequentialAnimation {
                PauseAnimation { duration: 90 }
                NumberAnimation {
                    target: c; property: "sweep"; from: 0; to: 1
                    duration: 420; easing.type: Easing.InOutSine
                }
                PropertyAction { target: c; property: "sweep"; value: 0 }
            }
        }
    }

    // The glint: copies of the title's letters in frost ink, seen through
    // three nested moving windows (wide and faint to narrow and bright), so
    // the letters light up as it passes without a band over the background.
    readonly property color glintInk: Theme.isLight ? Theme.accent : Theme.frostRim
    readonly property Item glint: Item {
        parent: c.title
        visible: c.title !== null && c.sweep > 0 && c.sweep < 1
        anchors.fill: parent
        readonly property real span: 46
        readonly property real centre: -span + c.sweep * ((c.title ? c.title.width : 0) + 2 * span)
        Repeater {
            model: [[1.0, 0.28], [0.55, 0.45], [0.22, 0.8]]
            delegate: Item {
                required property var modelData
                readonly property real w: c.glint.span * modelData[0]
                x: c.glint.centre - w / 2
                width: w
                height: parent.height
                clip: true
                opacity: modelData[1]
                Text {
                    x: -parent.x
                    text: c.title ? c.title.text : ""
                    font: c.title ? c.title.font : Qt.font({})
                    color: c.glintInk
                }
            }
        }
    }
}
