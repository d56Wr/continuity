import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    color: Theme.windowBg
    property bool composing: false
    signal composeFinished()
    signal callNumber(string number)

    function startCompose(number) {
        to.text = number
        phone.filterContacts(number)
        if (number) composer.forceActiveFocus(); else to.forceActiveFocus()
    }
    function focusComposer() { composer.forceActiveFocus() }

    readonly property bool hasThread: phone.threadId !== "" && !composing

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---------------------------------------------------------- header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 58
            color: Theme.windowBg
            visible: root.hasThread || root.composing

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 14
                spacing: 10
                visible: root.hasThread
                Avatar {
                    size: 34
                    source: phone.threadAvatar
                    initials: phone.threadTitle.length ? phone.threadTitle.split(" ").map(s => s[0]).join("").slice(0, 2).toUpperCase() : ""
                    color: "#8e8e93"
                }
                ColumnLayout {
                    spacing: 0
                    Layout.fillWidth: true
                    Label {
                        Layout.fillWidth: true
                        text: phone.threadTitle
                        font.weight: Font.DemiBold
                        color: Theme.text
                        elide: Text.ElideRight
                    }
                    Label {
                        visible: phone.threadNumber !== "" && phone.threadNumber !== phone.threadTitle
                        text: phone.threadNumber
                        color: Theme.secondary
                        font.pointSize: Theme.fontSize * 0.85
                    }
                }
                IconButton {
                    iconName: "call-start-symbolic"
                    tip: qsTr("Call")
                    tint: Theme.accent
                    visible: phone.threadNumber !== "" && phone.threadNumber.indexOf("@") < 0
                    enabled: phone.callsAvailable
                    onClicked: root.callNumber(phone.threadNumber)
                }
            }

            // compose header: "To:" field with contact suggestions
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 14
                visible: root.composing
                spacing: 8
                Label { text: qsTr("To:"); color: Theme.secondary }
                TextField {
                    id: to
                    Layout.fillWidth: true
                    placeholderText: qsTr("Name or phone number")
                    color: Theme.text
                    background: null
                    onTextEdited: phone.filterContacts(text)
                    Keys.onReturnPressed: composer.forceActiveFocus()
                    Keys.onDownPressed: suggestions.forceActiveFocus()
                }
                IconButton { iconName: "window-close-symbolic"; tip: qsTr("Cancel"); onClicked: root.composeFinished() }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.separator }
        }

        // contact suggestions while composing
        ListView {
            id: suggestions
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight, 260)
            visible: root.composing && to.activeFocus || root.composing && activeFocus
            clip: true
            model: root.composing ? phone.contacts : null
            delegate: ItemDelegate {
                width: suggestions.width
                height: 46
                highlighted: ListView.isCurrentItem && suggestions.activeFocus
                contentItem: RowLayout {
                    spacing: 10
                    Avatar { size: 30; source: model.avatar; initials: model.initials; color: model.color }
                    Label { text: model.name; color: Theme.text; font.weight: Font.DemiBold }
                    Label { text: model.number; color: Theme.secondary; Layout.fillWidth: true }
                }
                onClicked: pick()
                Keys.onReturnPressed: pick()
                function pick() {
                    to.text = model.number
                    const tid = phone.threadForNumber(model.number)
                    if (tid !== "") { root.composeFinished(); phone.openThread(tid) }
                    composer.forceActiveFocus()
                }
            }
        }

        // ---------------------------------------------------------- messages
        ListView {
            id: thread
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.hasThread
            clip: true
            model: phone.messages
            spacing: 0
            topMargin: 12
            bottomMargin: 12
            verticalLayoutDirection: ListView.TopToBottom
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            delegate: MessageBubble { width: thread.width }

            property bool stick: true
            onCountChanged: if (stick) Qt.callLater(positionViewAtEnd)
            onMovementEnded: stick = atYEnd
            onAtYBeginningChanged: if (atYBeginning && count > 0 && moving) phone.loadOlder()
            Connections {
                target: phone
                function onThreadChanged() { thread.stick = true; Qt.callLater(thread.positionViewAtEnd) }
            }
        }

        // empty state
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.hasThread && !root.composing
            ColumnLayout {
                anchors.centerIn: parent
                spacing: 10
                Kirigami.Icon {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 64; Layout.preferredHeight: 64
                    source: "mail-message-symbolic"
                    color: Theme.tertiary; isMask: true
                }
                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("Select a conversation")
                    color: Theme.secondary
                    font.pointSize: Theme.fontSize * 1.2
                }
            }
        }
        Item { Layout.fillHeight: true; visible: root.composing }

        // ---------------------------------------------------------- composer
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 14
            Layout.topMargin: 6
            spacing: 8
            visible: root.hasThread || root.composing

            IconButton {
                iconName: "mail-attachment-symbolic"
                tip: qsTr("Send photo or file")
                visible: phone.messageSource === "google" && root.hasThread
                onClicked: attachDialog.open()
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: Math.min(140, Math.max(36, composer.implicitHeight + 10))
                radius: 18
                color: "transparent"
                border.color: Theme.separator
                border.width: 1
                ScrollView {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    TextArea {
                        id: composer
                        placeholderText: phone.messageSource === "google" && phone.threadIsRcs
                                         ? qsTr("RCS Message") : qsTr("Text Message")
                        wrapMode: TextEdit.Wrap
                        color: Theme.text
                        background: null
                        verticalAlignment: TextEdit.AlignVCenter
                        Keys.onReturnPressed: (event) => {
                            if (event.modifiers & Qt.ShiftModifier) { event.accepted = false; return }
                            root.send()
                        }
                    }
                }
            }
            IconButton {
                iconName: "go-up-symbolic"
                size: 30
                filled: true
                fill: phone.messageSource === "google" && !phone.threadIsRcs && root.hasThread ? Theme.green : Theme.accent
                enabled: composer.text.trim() !== "" && (root.hasThread || to.text.trim() !== "")
                tip: qsTr("Send")
                onClicked: root.send()
            }
        }
    }

    FileDialog {
        id: attachDialog
        fileMode: FileDialog.OpenFiles
        title: qsTr("Send photo or file")
        onAccepted: phone.sendFilesToThread(selectedFiles)
    }
    DropArea {
        anchors.fill: parent
        enabled: phone.messageSource === "google" && root.hasThread
        onDropped: (d) => { if (d.hasUrls) phone.sendFilesToThread(d.urls) }
    }

    function send() {
        const text = composer.text.trim()
        if (!text) return
        if (root.composing) {
            if (!to.text.trim()) return
            phone.sendNew(to.text, text)
            const tid = phone.threadForNumber(to.text)
            root.composeFinished()
            if (tid !== "") phone.openThread(tid)
        } else {
            phone.sendReply(text)
        }
        composer.clear()
    }
}
