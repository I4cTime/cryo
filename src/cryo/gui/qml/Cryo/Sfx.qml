pragma Singleton
import QtQuick

// UI sound cues. A seam for the sound piece: call Sfx.play("mode"),
// Sfx.play("toggle_on") ... from anywhere; for now nothing plays.
QtObject {
    function play(name) {}
}
