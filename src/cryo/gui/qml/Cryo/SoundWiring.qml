import QtQuick

// Which machine events make a sound: the one place state cues are decided
// (Main.qml holds one instance). Controls add their own taps and toggles
// (CryoSwitch, CryoButton, IconButton); mode buttons need none, because the
// profile change they cause plays "mode" here.
//
// - profile changes (not the first frame of a connection)  -> "mode"
// - Thermal Guard engages / releases                       -> "freeze" / "thaw"
// - cryod lost / regained (not the first connect)          -> "disconnect" / "connect"
// - a command rejected or dropped (daemon.errorOccurred)   -> "error"
Item {
    id: wiring
    visible: false

    // What the last frame of this connection said; "" until one arrives.
    property string _profile: ""
    property bool _guard: false
    property bool _seen: false
    property bool _everConnected: false

    function _frame() {
        if (!daemon.connected)
            return
        if (!_seen) {
            // First frame of a connection: remember, say nothing.
            _seen = true
            _profile = daemon.profile
            _guard = daemon.guard
            return
        }
        if (daemon.profile !== _profile) {
            _profile = daemon.profile
            Sfx.play("mode")
        }
        if (daemon.guard !== _guard) {
            _guard = daemon.guard
            Sfx.play(_guard ? "freeze" : "thaw")
        }
    }

    Connections {
        target: daemon
        function onTelemetryChanged() { wiring._frame() }
        function onConnectedChanged() {
            if (daemon.connected) {
                if (wiring._everConnected)
                    Sfx.play("connect")
                wiring._everConnected = true
            } else {
                wiring._seen = false
                Sfx.play("disconnect")
            }
        }
        function onErrorOccurred(message) { Sfx.play("error") }
    }

    Component.onCompleted: {
        _everConnected = daemon.connected
        _frame()
    }
}
