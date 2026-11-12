import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Connection status line at the bottom of the window.
Label {
    Layout.fillWidth: true
    text: daemon.connected
          ? "cryod · " + daemon.profile + " profile"
          : "cryod unreachable - is the service running?  sudo systemctl start cryod"
    color: Theme.muted
    font.pixelSize: 10
    horizontalAlignment: Text.AlignHCenter
}
