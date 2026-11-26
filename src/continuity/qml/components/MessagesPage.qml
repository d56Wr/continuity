import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root
    signal callNumber(string number)

    property bool composing: false

    function focusSearch() { search.forceActiveFocus() }
    function openConversation(tid) { composing = false; phone.openThread(tid); chat.focusComposer() }
    function newMessage() { composing = true; chat.startCompose("") }
    function composeTo(number) {
        const tid = phone.threadForNumber(number)
        if (tid !== "") { composing = false; phone.openThread(tid); chat.focusComposer() }
        else { composing = true; chat.startCompose(number) }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---------------------------------------------------------- conversation list
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 320
            color: Theme.panelBg

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 12
                    Layout.bottomMargin: 8
                    spacing: 8
                    SearchBox {
                        id: search
                        Layout.fillWidth: true
                        onTextChanged: phone.filterConversations(text)
                    }
                    IconButton {
                        iconName: "document-edit-symbolic"
                        tip: qsTr("New message")
                        tint: Theme.accent
                        onClicked: root.newMessage()
                    }
                }

                // Google Messages is active in another browser/tab: offer to take it back
                Rectangle {
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 12
                    Layout.bottomMargin: 8
                    visible: phone.messageSource === "google" && phone.gmInactive
                    implicitHeight: inactiveRow.implicitHeight + 12
                    radius: 8
                    color: Qt.rgba(Theme.orange.r, Theme.orange.g, Theme.orange.b, 0.15)
                    RowLayout {
                        id: inactiveRow
                        anchors.fill: parent
                        anchors.margins: 6
                        anchors.leftMargin: 10
                        Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            text: qsTr("Google Messages is open somewhere else.")
                            color: Theme.text
                            font.pointSize: Theme.fontSize * 0.88
                        }
                        Button { text: qsTr("Use here"); onClicked: phone.gmActivate() }
                    }
                }

                // All / Unread filter (macOS-style segmented control)
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 12
                    Layout.bottomMargin: 8
                    spacing: 8
                    Segmented {
                        Layout.fillWidth: true
                        model: [qsTr("All"), phone.unreadCount > 0 ? qsTr("Unread (%1)").arg(phone.unreadCount) : qsTr("Unread")]
                        currentIndex: phone.unreadOnly ? 1 : 0
                        onActivated: (i) => phone.unreadOnly = (i === 1)
                    }
                    IconButton {
                        iconName: "mail-mark-read-symbolic"
                        tip: qsTr("Mark all as read")
                        enabled: phone.unreadCount > 0
                        onClicked: phone.markAllRead()
                    }
                }

                ListView {
                    id: list
                    Kirigami.WheelHandler { target: list; filterMouseEvents: true; keyNavigationEnabled: true }
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: phone.conversations
                    reuseItems: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    // like Messages on macOS: open the newest conversation on start
                    onCountChanged: if (count > 0 && phone.threadId === "" && !root.composing && search.text === "")
                                        phone.openThread(model.data(model.index(0, 0), 257))
                    // pinned conversations on top, with a header over each part
                    section.property: "section"
                    section.criteria: ViewSection.FullString
                    section.delegate: Item {
                        required property string section
                        width: list.width
                        height: phone.hasPinned ? (section === "pinned" ? 30 : 39) : 0
                        visible: phone.hasPinned
                        Rectangle {  // divider between pinned and the rest
                            visible: section !== "pinned"
                            anchors.top: parent.top; anchors.topMargin: 4
                            anchors.left: parent.left; anchors.leftMargin: 20
                            anchors.right: parent.right; anchors.rightMargin: 20
                            height: 1
                            color: Theme.separator
                        }
                        RowLayout {
                            anchors.left: parent.left; anchors.leftMargin: 20
                            anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                            spacing: 5
                            Kirigami.Icon {
                                visible: section === "pinned"
                                Layout.preferredWidth: 13; Layout.preferredHeight: 13
                                source: "window-pin-symbolic"
                                color: Theme.secondary; isMask: true
                            }
                            Label {
                                text: section === "pinned" ? qsTr("Pinned") : qsTr("Messages")
                                color: Theme.secondary
                                font.pointSize: Theme.fontSize * 0.85
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                    delegate: ConversationDelegate {
                        width: list.width
                        selected: !root.composing && model.threadId === phone.threadId
                        onClicked: { root.composing = false; phone.openThread(model.threadId) }
                    }
                    Label {
                        anchors.centerIn: parent
                        visible: list.count === 0
                        text: search.text ? qsTr("No results")
                            : phone.unreadOnly ? qsTr("No unread messages") : qsTr("No conversations yet")
                        color: Theme.secondary
                    }
                }
            }
        }

        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: Theme.separator }

        // ---------------------------------------------------------- chat
        ChatView {
            id: chat
            Layout.fillWidth: true
            Layout.fillHeight: true
            composing: root.composing
            onComposeFinished: root.composing = false
            onCallNumber: (n) => root.callNumber(n)
        }
    }
}
