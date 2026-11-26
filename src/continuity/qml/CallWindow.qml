import QtQuick
import "components"

// Floating call HUD above all windows (like the macOS call banner). It sits in the same corner
// as the message banners (which then make room below it) until dragged somewhere else.
// Shown only while there is a call; works with the main window hidden.
OverlayWindow {
    id: w
    placementKey: "call"
    followKey: "messages"
    contentWidth: banner.width
    contentHeight: banner.height
    shown: phone.callState !== ""
    onContentHeightChanged: phone.callBannerHeight = contentHeight

    // drag anywhere on the card that isn't a button (declared below the banner so buttons win)
    MouseArea {
        x: w.pad; y: w.pad
        width: banner.width; height: banner.height
        property point pressAt
        property bool moved: false
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        onPressed: (m) => { pressAt = Qt.point(m.x, m.y); moved = false }
        onPositionChanged: (m) => {
            // the card moves with the pointer, so the delta is always against the press point
            moved = true
            w.dragBy(Math.round(m.x - pressAt.x), Math.round(m.y - pressAt.y))
        }
        onReleased: if (moved) w.dragEnd()
    }

    CallBanner { id: banner; x: w.pad; y: w.pad }
}
