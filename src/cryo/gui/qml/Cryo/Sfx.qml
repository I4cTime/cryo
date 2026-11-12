pragma Singleton
import QtQuick

// UI sound cues: Sfx.play("mode"), Sfx.play("toggle_on") ... from anywhere.
//
// Off by default (Prefs.soundEnabled). The QtMultimedia side lives in
// SfxBank.qml and is created only while sound is on, so the audio backend is
// never initialized for someone who never turns sound on. If QtMultimedia
// cannot load, an effect fails to load or there is no audio output, the bank
// is dropped and `available` turns false: the Settings page says so and
// disables the sound controls; nothing else changes.
//
// What plays when is decided in one place, SoundWiring.qml (state cues), plus
// the control hooks in CryoSwitch, CryoButton and IconButton.
//
// A cue accepted while the bank is still loading (the "toggle_on" of the
// switch that just turned sound on) is held and plays as soon as the bank is
// ready, if that is within `pendingMs`. Turning sound off keeps the bank for
// `closeDelayMs`, so the switch's own "toggle_off" is heard to the end.
//
// Unavailable is not final while sound stays on: an output can appear later
// (session autostart before PipeWire, a headset plugged in after). The next
// accepted cue at least `retryMs` after the last failed attempt builds the
// bank again; no timer polls and nothing exists while idle. Until a retry
// is ready, `state` stays "unavailable" (Settings keeps saying so).
//
// Test hooks: with `dryRun` true nothing is created or played, but `played`
// still fires for every accepted cue, so tests and the tour can assert the
// triggers without making a sound. `_bankSource` names the bank component
// (tests point it at a fake bank).
QtObject {
    id: sfx

    readonly property var names: ["tap", "toggle_on", "toggle_off", "mode", "freeze",
                                  "thaw", "connect", "disconnect", "error"]
    readonly property var sets: ["ice", "glass", "deep"]
    property bool dryRun: false
    // "off" (sound off or dry run), "loading", "ready", "unavailable"
    readonly property string state: _state
    readonly property bool available: _state !== "unavailable"
    // Why it is unavailable (for the log and the tooltip), else "".
    readonly property string reason: _reason
    // The same cue does not restart within this many ms.
    readonly property int minGapMs: 60
    readonly property int pendingMs: 1500
    readonly property int closeDelayMs: 450
    readonly property int retryMs: 30000
    signal played(string name)

    property string _state: "off"
    property string _reason: ""
    property string _bankSource: "SfxBank.qml"
    property var _bank: null
    property real _failedAt: 0           // Date.now() of the last failed attempt
    property bool _retrying: false       // a retry bank is loading (state stays unavailable)
    property var _last: ({})
    property string _pending: ""
    property real _pendingAt: 0
    readonly property bool _wanted: Prefs.soundEnabled && !dryRun
    readonly property string _set: sets.indexOf(Prefs.soundSet) >= 0 ? Prefs.soundSet : "ice"
    // Slider position 0..1 to amplitude: squared, closer to how loud it sounds.
    readonly property real _volume: Math.max(0, Math.min(1, Prefs.soundVolume)) ** 2

    function play(name) {
        if (!Prefs.soundEnabled || names.indexOf(name) < 0)
            return
        const now = Date.now()
        if (now - (_last[name] || 0) < minGapMs)
            return
        _last[name] = now
        played(name)
        if (_bank === null && _state === "unavailable" && _wanted && now - _failedAt >= retryMs) {
            _retrying = true
            _open()
        }
        if (_bank === null)
            return
        if (_state === "ready") {
            _bank.play(name)
        } else {                         // loading, or a retry still loading
            _pending = name
            _pendingAt = now
        }
    }

    on_WantedChanged: {
        if (_wanted) {
            _closeLater.stop()
            _open()
        } else if (_bank !== null) {
            _closeLater.restart()
        } else {
            _close()
        }
    }
    readonly property Timer _closeLater: Timer {
        interval: sfx.closeDelayMs
        onTriggered: if (!sfx._wanted) sfx._close()
    }
    Component.onCompleted: if (_wanted) _open()

    function _open() {
        if (_bank !== null)
            return
        const component = Qt.createComponent(_bankSource)
        if (component.status !== Component.Ready) {
            _fail(component.errorString().trim() || "QtMultimedia did not load")
            return
        }
        const bank = component.createObject(sfx, {
            "soundSet": Qt.binding(() => sfx._set),
            "volume": Qt.binding(() => sfx._volume)
        })
        if (bank === null) {
            _fail("the sound bank could not be created")
            return
        }
        _bank = bank
        if (!_retrying) {
            _reason = ""
            _state = "loading"
        }
        bank.updated.connect(_bankState)
        _bankState()
    }
    function _bankState() {
        if (_bank === null)
            return
        if (_bank.failed !== "") {
            _fail(_bank.failed)
            return
        }
        if (!_bank.ready) {
            if (!_retrying)
                _state = "loading"
            return
        }
        _retrying = false
        _reason = ""
        _state = "ready"
        if (_pending !== "") {
            if (Date.now() - _pendingAt <= pendingMs)
                _bank.play(_pending)
            _pending = ""
        }
    }
    function _fail(why) {
        console.info("cryo: sound unavailable: " + why)
        _close()
        _reason = why
        _state = "unavailable"
        _failedAt = Date.now()
    }
    function _close() {
        _closeLater.stop()
        _retrying = false
        _pending = ""
        if (_bank !== null) {
            _bank.destroy()
            _bank = null
        }
        // An unavailable verdict stands until sound is turned on again or a
        // retry (see play) comes up ready.
        if (_state !== "unavailable" || _wanted)
            _state = "off"
    }
}
