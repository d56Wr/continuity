import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Stack of banners (macOS style) for texts and other phone notifications: click to open the
// conversation / notification list, "Reply" to answer inline, "Copy code" for one-time security
// codes. Newest on top, max 3; a newer banner from the same conversation or app replaces the older.
Item {
    id: root
    width: 380
    implicitHeight: col.implicitHeight
    height: implicitHeight
    readonly property int count: banners.count
    property bool interacting: false   // a reply field is open (the window wants keyboard focus)
    signal dragBy(int dx, int dy)      // the user drags a banner: move the whole window
    signal dragFinished()

    ListModel { id: banners }

    property bool growUp: false        // newest at the bottom (banners placed low on the screen)

    function push(m) {
        for (let i = 0; i < banners.count; i++)
            if (banners.get(i).threadId === m.threadId) { banners.remove(i); break }
        // the newest banner sits next to the screen edge the window is attached to
        if (growUp) banners.append(m); else banners.insert(0, m)
        while (banners.count > 3) banners.remove(growUp ? 0 : banners.count - 1)
    }
    function removeId(id) {
        for (let i = 0; i < banners.count; i++)
            if (banners.get(i).id === id) { banners.remove(i); return }
    }

    Connections { target: phone; function onMessageArrived(m) { root.push(m) } }

    Column {
        id: col
        width: parent.width
        spacing: 10

        Repeater {
            model: banners
            delegate: Item {
                id: banner
                required property string id
                required property string threadId
                required property string title
                required property string body
                required property string avatar
                required property string initials
                required property string color
                required property string code
                required property string kind    // "message", "notification" or "test"
                required property string nid     // phone notification id (kind "notification")
                required property string app
                required property bool canReply
                property bool replying: false
                property bool copied: false
                property bool sent: false
                width: col.width
                height: card.height
                onReplyingChanged: root.interacting = replying

                function close() { root.interacting = false; root.removeId(id) }
                // handled (code copied / replied): read on the phone, notification cleared
                function done() {
                    if (kind === "message") phone.markBannerRead(id, threadId, body)
                    else if (kind === "notification") phone.dismiss(nid)
                }

                Timer {   // fade out unless the user is busy with it (or banners stay until closed)
                    // a code (or the test banner) stays at least 30 s, time enough to use it
                    interval: banner.code !== "" || banner.kind === "test"
                              ? Math.max(30, phone.bannerSeconds) * 1000 : phone.bannerSeconds * 1000
                    running: phone.bannerSeconds > 0 && !hover.hovered && !banner.replying
                    onTriggered: banner.close()
                }
                Timer { id: closeSoon; interval: 1200; onTriggered: banner.close() }

                MultiEffect {
                    source: card; anchors.fill: card
                    shadowEnabled: true; shadowBlur: 1.0; shadowColor: Theme.shadow; shadowVerticalOffset: 5
                }
                Rectangle {
                    id: card
                    width: parent.width
                    height: content.implicitHeight + 24
                    radius: 18
                    color: Theme.dark ? "#2c2c2e" : "#ffffff"
                    border.color: Theme.separator

                    HoverHandler { id: hover }
                    MouseArea {   // click = open the conversation, drag = move the banners
                        anchors.fill: parent
                        property point pressAt
                        property bool moved: false
                        cursorShape: moved ? Qt.ClosedHandCursor : Qt.PointingHandCursor
                        onPressed: (m) => { pressAt = Qt.point(m.x, m.y); moved = false }
                        onPositionChanged: (m) => {
                            const dx = m.x - pressAt.x, dy = m.y - pressAt.y
                            if (!moved && Math.abs(dx) + Math.abs(dy) < 6) return
                            moved = true
                            root.dragBy(Math.round(dx), Math.round(dy))
                        }
                        onReleased: moved ? root.dragFinished() : null
                        onClicked: {
                            if (moved) return
                            if (banner.kind === "message") phone.showThread(banner.threadId)
                            else if (banner.kind === "notification") phone.showNotifications()
                            banner.close()
                        }
                    }

                    ColumnLayout {
                        id: content
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                        spacing: 8

                        RowLayout {
                            spacing: 10
                            Avatar {
                                Layout.alignment: Qt.AlignTop
                                size: 40
                                source: banner.avatar; initials: banner.initials; color: banner.color
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                RowLayout {
                                    Label {
                                        Layout.fillWidth: true
                                        text: banner.title
                                        font.weight: Font.DemiBold
                                        color: Theme.text
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: banner.app !== "" ? banner.app + " · " + qsTr("now") : qsTr("now")
                                        color: Theme.secondary
                                        font.pointSize: Theme.fontSize * 0.85
                                        elide: Text.ElideRight
                                        Layout.maximumWidth: 150
                                    }
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: banner.sent ? qsTr("Reply sent") : banner.body
                                    color: banner.sent ? Theme.green : Theme.text
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 4
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        // one-time code: big digits + copy (Security Code AutoFill)
                        RowLayout {
                            visible: banner.code !== ""
                            Layout.fillWidth: true
                            spacing: 10
                            Label {
                                Layout.fillWidth: true
                                text: banner.code
                                font.pointSize: Theme.fontSize * 1.5
                                font.weight: Font.DemiBold
                                font.letterSpacing: 2
                                font.features: { "tnum": 1 }
                                color: Theme.text
                            }
                            PillButton {   // Reply sits next to Copy Code on a code banner
                                visible: banner.canReply && !banner.replying && !banner.sent
                                text: qsTr("Reply")
                                onClicked: { banner.replying = true; reply.forceActiveFocus() }
                            }
                            PillButton {
                                text: banner.copied ? qsTr("Copied ✓") : qsTr("Copy Code")
                                primary: !banner.copied
                                onClicked: {
                                    phone.copySilently(banner.code)
                                    banner.done()
                                    banner.copied = true
                                    closeSoon.restart()
                                }
                            }
                        }

                        // inline reply
                        RowLayout {
                            visible: banner.replying
                            Layout.fillWidth: true
                            spacing: 8
                            TextField {
                                id: reply
                                Layout.fillWidth: true
                                color: Theme.text
                                placeholderTextColor: Theme.secondary
                                background: Rectangle { radius: 14; color: Theme.fieldBg; border.color: reply.activeFocus ? Theme.accent : "transparent" }
                                leftPadding: 12; rightPadding: 12
                                placeholderText: qsTr("Reply…")
                                Keys.onEscapePressed: banner.replying = false
                                onAccepted: send()
                                function send() {
                                    if (text.trim() === "") return
                                    if (banner.kind === "notification") phone.replyNotification(banner.nid, text)
                                    else phone.replyToThread(banner.threadId, text)
                                    banner.done()
                                    text = ""
                                    banner.replying = false
                                    banner.sent = true
                                    closeSoon.restart()
                                }
                            }
                            IconButton {
                                size: 30; iconName: "document-send-symbolic"; filled: true; fill: Theme.accent
                                enabled: reply.text.trim() !== ""
                                tip: qsTr("Send"); onClicked: reply.send()
                            }
                        }

                        // actions on hover (a code banner has them next to the code instead)
                        RowLayout {
                            visible: banner.code === "" && banner.kind !== "test" && !banner.replying
                                     && !banner.sent && hover.hovered
                            Layout.fillWidth: true
                            spacing: 8
                            Item { Layout.fillWidth: true }
                            PillButton {   // texts: read (also on the phone); app notifications: clear on the phone
                                text: banner.kind === "message" ? qsTr("Mark as Read") : qsTr("Clear")
                                onClicked: { banner.done(); banner.close() }
                            }
                            PillButton {
                                visible: banner.canReply
                                text: qsTr("Reply")
                                onClicked: { banner.replying = true; reply.forceActiveFocus() }
                            }
                        }
                    }

                    // close (×) in the top-left corner on hover, like macOS
                    IconButton {
                        visible: hover.hovered
                        x: -6; y: -6
                        size: 22; iconScale: 0.55
                        iconName: "window-close-symbolic"
                        filled: true; fill: Theme.dark ? "#48484a" : "#8e8e93"
                        tip: qsTr("Close")
                        onClicked: banner.close()
                    }
                }
            }
        }
    }
}
