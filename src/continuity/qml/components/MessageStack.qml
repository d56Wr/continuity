import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Stack of incoming-message banners (macOS style): click to open the conversation,
// "Reply" to answer inline, "Copy code" for one-time security codes. Newest on top, max 3.
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

    function push(m) {
        for (let i = 0; i < banners.count; i++)
            if (banners.get(i).threadId === m.threadId) { banners.remove(i); break }
        banners.insert(0, m)
        while (banners.count > 3) banners.remove(banners.count - 1)
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
                property bool replying: false
                property bool copied: false
                property bool sent: false
                width: col.width
                height: card.height
                onReplyingChanged: root.interacting = replying

                function close() { root.interacting = false; root.removeId(id) }

                Timer {   // fade out unless the user is busy with it
                    interval: banner.code !== "" ? 30000 : 9000
                    running: !hover.hovered && !banner.replying
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
                        onClicked: if (!moved) { phone.showThread(banner.threadId); banner.close() }
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
                                    Label { text: qsTr("now"); color: Theme.secondary; font.pointSize: Theme.fontSize * 0.85 }
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
                            PillButton {
                                text: banner.copied ? qsTr("Copied ✓") : qsTr("Copy Code")
                                primary: !banner.copied
                                onClicked: {
                                    phone.copySilently(banner.code)
                                    phone.markBannerRead(banner.id, banner.threadId, banner.body)
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
                                    phone.replyToThread(banner.threadId, text)
                                    phone.markBannerRead(banner.id, banner.threadId, banner.body)
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

                        RowLayout {
                            visible: !banner.replying && !banner.sent && (hover.hovered || banner.code !== "")
                            Layout.fillWidth: true
                            spacing: 8
                            Item { Layout.fillWidth: true }
                            PillButton {
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
