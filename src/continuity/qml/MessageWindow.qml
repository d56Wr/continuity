import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell
import "components"

// Floating banners for incoming messages (layer-shell overlay, top-right by default).
// Drag it anywhere; the offset from the top-right screen corner is remembered.
Window {
    id: w
    readonly property int pad: 16
    property int offRight: 0
    property int offTop: 0
    width: stack.width + 2 * pad
    height: Math.max(1, stack.height + 2 * pad)
    color: "transparent"
    flags: Qt.FramelessWindowHint
    visible: stack.count > 0

    LayerShell.Window.scope: "continuity-messages"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorRight
    // keyboard only while typing a reply, so banners never steal focus from the game/editor
    LayerShell.Window.keyboardInteractivity: stack.interacting ? LayerShell.Window.KeyboardInteractivityOnDemand
                                                               : LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: 0
    LayerShell.Window.activateOnShow: false
    LayerShell.Window.wantsToBeOnActiveScreen: true

    function place() {
        offRight = Math.max(0, Math.min(offRight, Screen.width - width))
        offTop = Math.max(0, Math.min(offTop, Screen.height - height))
        LayerShell.Window.margins = { left: 0, top: offTop, right: offRight, bottom: 0 }
    }
    Component.onCompleted: {
        const p = phone.windowPlacement("messages")
        offRight = p.right || 0
        offTop = p.top || 0
        place()
    }
    onVisibleChanged: if (visible) place()
    onHeightChanged: if (visible) place()

    MouseArea {   // drag by any empty spot (between/around banners)
        anchors.fill: parent
        property point pressAt
        property bool moved: false
        cursorShape: pressed && moved ? Qt.ClosedHandCursor : Qt.ArrowCursor
        onPressed: (m) => { pressAt = Qt.point(m.x, m.y); moved = false }
        onPositionChanged: (m) => {
            moved = true
            w.offRight -= Math.round(m.x - pressAt.x)
            w.offTop += Math.round(m.y - pressAt.y)
            w.place()
        }
        onReleased: if (moved) phone.saveWindowPlacement("messages", { right: w.offRight, top: w.offTop })
    }

    MessageStack {
        id: stack; x: w.pad; y: w.pad
        onDragBy: (dx, dy) => { w.offRight -= dx; w.offTop += dy; w.place() }
        onDragFinished: phone.saveWindowPlacement("messages", { right: w.offRight, top: w.offTop })
    }
}
