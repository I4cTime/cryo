import QtQuick
import QtMultimedia

// The playing half of Sfx: one SoundEffect per cue for the current set.
// Created by Sfx.qml only while sound is on (this file is what pulls in
// QtMultimedia, so it is never loaded otherwise). Changing `soundSet`
// reloads every effect from src/cryo/gui/assets/sounds/<set>/<cue>.wav.
QtObject {
    id: bank
    property string soundSet: "ice"
    property real volume: 0.36
    // All effects loaded and an output exists / why the bank cannot play.
    readonly property bool ready: _effects.length > 0 && _loaded === _effects.length && failed === ""
    readonly property string failed: devices.audioOutputs.length === 0
                                     ? "no audio output device"
                                     : _errors.length > 0 ? "could not load " + _errors.join(", ") : ""
    signal updated()
    onReadyChanged: updated()
    onFailedChanged: updated()

    function play(name) {
        const effect = _byName[name]
        if (effect !== undefined && effect.status === SoundEffect.Ready)
            effect.play()
    }

    property int _loaded: 0
    property var _errors: []
    property var _byName: ({})
    function _recount() {
        let loaded = 0
        const errors = []
        for (const effect of _effects) {
            if (effect.status === SoundEffect.Ready)
                loaded++
            else if (effect.status === SoundEffect.Error)
                errors.push(soundSet + "/" + effect.cue + ".wav")
        }
        _loaded = loaded
        _errors = errors
    }

    readonly property MediaDevices devices: MediaDevices {}
    readonly property Component _cue: Component {
        SoundEffect {
            property string cue
            source: Qt.resolvedUrl("../../assets/sounds/" + bank.soundSet + "/" + cue + ".wav")
            volume: bank.volume
            onStatusChanged: bank._recount()
        }
    }
    property var _effects: []

    Component.onCompleted: {
        const made = []
        const byName = {}
        for (const name of Sfx.names) {
            const effect = _cue.createObject(bank, { "cue": name })
            made.push(effect)
            byName[name] = effect
        }
        _effects = made
        _byName = byName
        _recount()
        updated()
    }
}
