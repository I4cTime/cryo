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
// Test hook: with `dryRun` true nothing is created or played, but `played`
// still fires for every accepted cue, so tests and the tour can assert the
// triggers without making a sound.
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
    signal played(string name)

    property string _state: "off"
    property string _reason: ""
    property var _bank: null
    property var _last: ({})
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
        if (_bank !== null && _state === "ready")
            _bank.play(name)
    }

    on_WantedChanged: _wanted ? _open() : _close()
    Component.onCompleted: if (_wanted) _open()

    function _open() {
        if (_bank !== null)
            return
        const component = Qt.createComponent("SfxBank.qml")
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
        _reason = ""
        _state = "loading"
        bank.updated.connect(_bankState)
        _bankState()
    }
    function _bankState() {
        if (_bank === null)
            return
        if (_bank.failed !== "")
            _fail(_bank.failed)
        else
            _state = _bank.ready ? "ready" : "loading"
    }
    function _fail(why) {
        console.info("cryo: sound unavailable: " + why)
        _close()
        _reason = why
        _state = "unavailable"
    }
    function _close() {
        if (_bank !== null) {
            _bank.destroy()
            _bank = null
        }
        // An unavailable verdict stands until sound is turned on again.
        if (_state !== "unavailable" || _wanted)
            _state = "off"
    }
}
