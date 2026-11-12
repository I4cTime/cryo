import QtQuick

// A live figure whose digits roll: each character cell that changes slides
// its old glyph out and the new one in vertically (up for a bigger value,
// down for a smaller one, 280 ms OutCubic), clipped to the cell. Digit cells
// share one width (the widest digit of the font), so the figure never
// jitters sideways. Cells are right aligned and kept alive across updates,
// so only the characters that changed move. Without motion (reduce motion,
// unfocused or hidden window) every cell shows its new character at once,
// the plain text.
Item {
    id: roll
    property string text
    property font font
    property color color
    // Character cells kept alive, right aligned (longer text is not drawn).
    property int slots: 6
    readonly property int duration: 280

    // What the cells show, and which way they roll (+1 bigger, -1 smaller).
    // Both are set together in onTextChanged so a cell never sees one
    // without the other.
    property string shown
    property int dir: 1
    onTextChanged: {
        const a = parseFloat(shown), b = parseFloat(text)
        dir = (isNaN(a) || isNaN(b) || b >= a) ? 1 : -1
        shown = text
    }
    Component.onCompleted: shown = text
    // True while any cell is mid-roll (tests).
    readonly property bool rolling: rollingCells > 0
    property int rollingCells: 0

    FontMetrics { id: fm; font: roll.font }
    readonly property real digitWidth: {
        let w = 0
        for (let d = 0; d < 10; d++)
            w = Math.max(w, fm.advanceWidth(String(d)))
        return Math.ceil(w)
    }
    readonly property real lineHeight: Math.ceil(fm.height)

    implicitWidth: cells.implicitWidth
    implicitHeight: lineHeight

    Row {
        id: cells
        Repeater {
            model: roll.slots
            delegate: Item {
                id: cell
                objectName: "rollCell"
                required property int index
                readonly property string ch: {
                    const i = roll.shown.length - roll.slots + index
                    return i >= 0 ? roll.shown.charAt(i) : ""
                }
                readonly property bool isDigit: ch.length === 1 && ch >= "0" && ch <= "9"
                // what is drawn: `cur` settled, `old` leaving while p < 1
                property string cur: ""
                property string old: ""
                property int dir: 1
                property real p: 1
                width: ch === "" ? 0 : isDigit ? roll.digitWidth : Math.ceil(fm.advanceWidth(ch))
                height: roll.lineHeight
                clip: true
                visible: width > 0

                onChChanged: {
                    if (Ambient.motion && cur !== "" && ch !== "" && ch !== cur) {
                        old = cur
                        dir = roll.dir
                        slide.restart()
                    } else {
                        slide.stop()
                        p = 1
                    }
                    cur = ch
                }
                Component.onCompleted: cur = ch

                NumberAnimation {
                    id: slide
                    target: cell; property: "p"; from: 0; to: 1
                    duration: roll.duration; easing.type: Easing.OutCubic
                    onRunningChanged: roll.rollingCells += running ? 1 : -1
                }
                Text {
                    objectName: "rollCur"
                    width: cell.width
                    horizontalAlignment: Text.AlignHCenter
                    y: (1 - cell.p) * cell.height * cell.dir
                    text: cell.cur
                    font: roll.font
                    color: roll.color
                }
                Text {
                    width: cell.width
                    horizontalAlignment: Text.AlignHCenter
                    y: -cell.p * cell.height * cell.dir
                    visible: cell.p < 1
                    text: cell.old
                    font: roll.font
                    color: roll.color
                }
            }
        }
    }
}
