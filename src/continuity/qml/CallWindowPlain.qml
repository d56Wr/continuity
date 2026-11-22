import QtQuick
import QtQuick.Window
import "components"

// Fallback without layer-shell (X11, or LayerShellQt not installed): a frameless always-on-top
// tool window. Drag to move; the position is remembered.
Window {
    id: w
    readonly property int pad: 16
    width: banner.width + 2 * pad
    height: banner.height + 2 * pad
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: phone.callState !== ""

    Component.onCompleted: {
        const p = phone.windowPlacement("callPlain")
        x = p.x !== undefined ? p.x : Screen.virtualX + Screen.width - width
        y = p.y !== undefined ? p.y : Screen.virtualY
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        onPressed: w.startSystemMove()
    }
    Timer { id: save; interval: 400; onTriggered: phone.saveWindowPlacement("callPlain", { x: w.x, y: w.y }) }
    onXChanged: if (visible) save.restart()
    onYChanged: if (visible) save.restart()

    CallBanner { id: banner; x: w.pad; y: w.pad }
}
