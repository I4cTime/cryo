pragma Singleton
import QtQuick

// Runtime state every component may react to. A singleton cannot see the
// window or the `daemon` context property, so Main.qml pushes `live` and
// `connected` in with Bindings.
QtObject {
    // The window is on screen and focused (Main.qml computes it; when
    // forceLive is set it pushes true regardless).
    property bool live: false
    // Test hook: offscreen and headless windows are never focused, so the
    // tour and tests set this to see the app as a focused user does.
    property bool forceLive: false
    // Gate for every looping or easing animation. Equals live for now; a
    // reduce-motion preference will be ANDed in here.
    readonly property bool motion: live
    // cryod reachable (mirrors daemon.connected).
    property bool connected: false
}
