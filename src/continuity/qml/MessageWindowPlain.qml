import QtQuick
import QtQuick.Window
import "components"

// Fallback without layer-shell: frameless always-on-top tool window.
Window {
    id: w
    readonly property int pad: 16
    width: stack.width + 2 * pad
    height: Math.max(1, stack.height + 2 * pad)
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    visible: stack.count > 0

    Component.onCompleted: {
        const p = phone.windowPlacement("messagesPlain")
        x = p.x !== undefined ? p.x : Screen.virtualX + Screen.width - width
        y = p.y !== undefined ? p.y : Screen.virtualY
    }
    MouseArea { anchors.fill: parent; onPressed: w.startSystemMove() }
    Timer { id: save; interval: 400; onTriggered: phone.saveWindowPlacement("messagesPlain", { x: w.x, y: w.y }) }
    onXChanged: if (visible) save.restart()
    onYChanged: if (visible) save.restart()

    MessageStack {
        id: stack; x: w.pad; y: w.pad
        onDragBy: (dx, dy) => { w.x += dx; w.y += dy }
    }
}
