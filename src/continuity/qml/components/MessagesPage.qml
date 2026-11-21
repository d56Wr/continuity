import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root
    signal callNumber(string number)

    property bool composing: false

    function focusSearch() { search.forceActiveFocus() }
    function newMessage() { composing = true; chat.startCompose("") }
    function composeTo(number) {
        const tid = phone.threadForNumber(number)
        if (tid >= 0) { composing = false; phone.openThread(tid); chat.focusComposer() }
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

                ListView {
                    id: list
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: phone.conversations
                    reuseItems: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    // like Messages on macOS: open the newest conversation on start
                    onCountChanged: if (count > 0 && phone.threadId < 0 && !root.composing && search.text === "")
                                        phone.openThread(model.data(model.index(0, 0), 257))
                    delegate: ConversationDelegate {
                        width: list.width
                        selected: !root.composing && model.threadId === phone.threadId
                        onClicked: { root.composing = false; phone.openThread(model.threadId) }
                    }
                    Label {
                        anchors.centerIn: parent
                        visible: list.count === 0
                        text: search.text ? qsTr("No results") : qsTr("No conversations yet")
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
