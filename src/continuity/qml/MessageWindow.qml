import QtQuick
import "components"

// Floating banners for messages and phone notifications, top-right by default. Drag them
// anywhere. In the top half of the screen new banners stack downwards (newest on top), in the
// bottom half they grow upwards (newest at the bottom, next to the screen edge).
OverlayWindow {
    id: w
    placementKey: "messages"
    contentWidth: stack.width
    contentHeight: stack.height
    shown: stack.count > 0
    wantsKeyboard: stack.interacting

    MessageStack {
        id: stack; x: w.pad; y: w.pad
        growUp: w.atBottom
        onDragBy: (dx, dy) => w.dragBy(dx, dy)
        onDragFinished: w.dragEnd()
    }
}
