import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell
import "components"

// Floating call HUD above all windows (wlr-layer-shell, like the macOS call banner).
// Shown only while there is a call; works with the main window hidden.
// Drag it anywhere; the offset from the top-right screen corner is remembered.
Window {
    id: w
    readonly property int pad: 16   // transparent room for the shadow
    property int offRight: 0        // distance of the window from the right screen edge
    property int offTop: 0          // ... and from the top edge (both below/beside panels)
    width: banner.width + 2 * pad
    height: banner.height + 2 * pad
    color: "transparent"
    flags: Qt.FramelessWindowHint
    visible: phone.callState !== ""

    LayerShell.Window.scope: "continuity-call"
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorRight
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: 0
    LayerShell.Window.activateOnShow: false
    LayerShell.Window.wantsToBeOnActiveScreen: true

    function place() {
        // keep it on screen even if the remembered spot came from a bigger monitor
        offRight = Math.max(0, Math.min(offRight, Screen.width - width))
        offTop = Math.max(0, Math.min(offTop, Screen.height - height))
        LayerShell.Window.margins = { left: 0, top: offTop, right: offRight, bottom: 0 }
    }

    Component.onCompleted: {
        const p = phone.windowPlacement("call")
        offRight = p.right || 0
        offTop = p.top || 0
        place()
    }
    onVisibleChanged: if (visible) place()

    // drag anywhere on the card that isn't a button (declared below the banner so buttons win)
    MouseArea {
        anchors.fill: parent
        property point pressAt
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        onPressed: (m) => pressAt = Qt.point(m.x, m.y)
        onPositionChanged: (m) => {
            // the surface follows the pointer, so the delta is always against the press point
            w.offRight -= Math.round(m.x - pressAt.x)
            w.offTop += Math.round(m.y - pressAt.y)
            w.place()
        }
        onReleased: phone.saveWindowPlacement("call", { right: w.offRight, top: w.offTop })
    }

    CallBanner { id: banner; x: w.pad; y: w.pad }
}
