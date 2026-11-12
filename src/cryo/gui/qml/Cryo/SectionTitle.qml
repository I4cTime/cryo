import QtQuick
import QtQuick.Controls.Basic

// A section heading. It sits straight on the backdrop, so a Clearing melts
// the window frost back around it (no panel behind it to keep it legible).
Label {
    color: Theme.muted
    font.pixelSize: 11
    font.letterSpacing: 2
    font.bold: true
    Clearing { objectName: "clearing" }
}
