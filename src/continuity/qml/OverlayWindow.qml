import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

// A floating layer-shell overlay (call HUD, banners) that can be dragged anywhere.
//
// The overlay covers the whole screen but only takes input where its content is, so the
// content moves inside it smoothly (moving a layer surface itself lags behind the pointer on
// Wayland and overshoots). The content sticks to the nearest screen corner and the distance
// from it is remembered under `placementKey`. `atBottom` tells content placed in the bottom
// half, e.g. so a stack can grow upwards.
Window {
    id: w
    required property string placementKey
    property int contentWidth: 0     // size of the content (without the shadow padding)
    property int contentHeight: 0
    property bool shown: false
    property bool wantsKeyboard: false
    readonly property int pad: 16    // room for the shadow around the content
    property bool atLeft: false      // stuck to the left edge (else the right one)
    property bool atBottom: false    // stuck to the bottom edge (else the top one)
    property int offX: 0             // distance from that left/right edge
    property int offY: 0             // distance from that top/bottom edge
    property string followKey: ""    // until moved itself, sit where this other overlay sits
    property int extraY: 0           // push the content further from its top/bottom edge
    default property alias content: holder.data

    width: Screen.width
    height: Screen.height
    color: "transparent"
    flags: Qt.FramelessWindowHint
    visible: shown

    LayerShell.Window.scope: "continuity-" + placementKey
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorBottom
                             | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight
    // keyboard only when asked (typing a reply), so it never steals focus from a game/editor
    LayerShell.Window.keyboardInteractivity: wantsKeyboard ? LayerShell.Window.KeyboardInteractivityOnDemand
                                                           : LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: 0   // stay clear of panels
    LayerShell.Window.activateOnShow: false
    LayerShell.Window.wantsToBeOnActiveScreen: true

    function clampX(v) { return Math.max(0, Math.min(v, w.width - holder.width)) }
    function clampY(v) { return Math.max(0, Math.min(v, w.height - holder.height)) }

    // the content's spot, from the corner it is stuck to (follows its size)
    readonly property int homeX: clampX(atLeft ? offX : w.width - holder.width - offX)
    readonly property int homeY: clampY(atBottom ? w.height - holder.height - offY - extraY : offY + extraY)

    // move by a pointer delta while dragging
    function dragBy(dx, dy) {
        holder.x = clampX(holder.x + dx)   // breaks the binding to homeX until dragEnd()
        holder.y = clampY(holder.y + dy)
    }
    // after a drag: stick to the nearest corner, keeping the content where it is
    function dragEnd() {
        const left = holder.x, top = holder.y
        atLeft = left + holder.width / 2 < w.width / 2
        atBottom = top + holder.height / 2 > w.height / 2
        offX = atLeft ? left : w.width - holder.width - left
        offY = atBottom ? w.height - holder.height - top : top
        holder.x = Qt.binding(() => w.homeX)
        holder.y = Qt.binding(() => w.homeY)
        phone.saveWindowPlacement(placementKey, { x: offX, y: offY, left: atLeft ? 1 : 0, bottom: atBottom ? 1 : 0 })
    }
    function updateInput() {
        phone.setInputRegion(w, holder.x + pad, holder.y + pad, contentWidth, contentHeight)
    }

    function loadPlacement() {
        let p = phone.windowPlacement(placementKey)
        if (Object.keys(p).length === 0 && followKey !== "") p = phone.windowPlacement(followKey)
        if (Object.keys(p).length === 0) return   // default: top-right
        atLeft = !!p.left
        atBottom = !!p.bottom
        offX = p.x !== undefined ? p.x : (p.right || 0)   // older versions saved {right, top}
        offY = p.y !== undefined ? p.y : (p.top || 0)
    }
    Connections {
        target: phone
        function onPlacementChanged(key) {
            if (key === w.followKey && Object.keys(phone.windowPlacement(w.placementKey)).length === 0)
                w.loadPlacement()
        }
    }
    Component.onCompleted: {
        loadPlacement()
        updateInput()
    }
    onVisibleChanged: if (visible) updateInput()
    onContentWidthChanged: updateInput()
    onContentHeightChanged: updateInput()

    Item {
        id: holder
        x: w.homeX
        y: w.homeY
        width: w.contentWidth + 2 * w.pad
        height: w.contentHeight + 2 * w.pad
        onXChanged: w.updateInput()
        onYChanged: w.updateInput()
    }
}
