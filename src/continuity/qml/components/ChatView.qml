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
    readonly property bool canAttach: phone.messageSource === "google" && hasThread

    // photos and files waiting to be sent with the next message (pasted with Ctrl+V)
    property var pending: []
    function addPending(urls) {
        const next = root.pending.slice()
        for (const u of urls) if (next.indexOf(String(u)) < 0) next.push(String(u))
        root.pending = next
    }
    function removePending(i) { const next = root.pending.slice(); next.splice(i, 1); root.pending = next }
    function isImage(u) { return /\.(png|jpe?g|gif|webp|bmp|heic|avif)$/i.test(u) }
    function fileName(u) { return decodeURIComponent(String(u).split("/").pop()) }
    property string pendingFor: phone.threadId
    onPendingForChanged: root.pending = []

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
                // new messages in the open conversation stay unread until you say so (or reply)
                PillButton {
                    text: qsTr("Mark as Read")
                    primary: true
                    visible: phone.threadUnread
                    onClicked: phone.markRead(phone.threadId)
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
            Kirigami.WheelHandler { target: suggestions; filterMouseEvents: true; keyNavigationEnabled: true }
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
            Kirigami.WheelHandler { target: thread; filterMouseEvents: true; keyNavigationEnabled: true }
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
            property bool autoPositioning: false
            function toEnd() { autoPositioning = true; positionViewAtEnd(); autoPositioning = false }
            onCountChanged: if (stick) Qt.callLater(toEnd)
            onContentYChanged: {
                if (autoPositioning) return
                stick = atYEnd
                if (atYBeginning && count > 0 && contentHeight > height) olderTimer.restart()
            }
            Timer { id: olderTimer; interval: 250; onTriggered: if (thread.atYBeginning) phone.loadOlder() }
            Connections {
                target: phone
                function onThreadChanged() { thread.stick = true; Qt.callLater(thread.toEnd) }
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

        // ---------------------------------------------------------- pending attachments
        Flickable {
            Layout.fillWidth: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 6
            Layout.preferredHeight: 76
            visible: root.pending.length > 0 && root.canAttach
            contentWidth: pendingRow.width
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Row {
                id: pendingRow
                spacing: 8
                Repeater {
                    model: root.pending
                    delegate: Item {
                        required property string modelData
                        required property int index
                        width: root.isImage(modelData) ? 76 : 180
                        height: 76
                        Rectangle {
                            anchors.fill: parent
                            anchors.topMargin: 6; anchors.rightMargin: 6
                            radius: 10
                            color: Theme.hover
                            border.color: Theme.separator
                            clip: true
                            Image {
                                anchors.fill: parent
                                visible: root.isImage(modelData)
                                source: visible ? modelData : ""
                                fillMode: Image.PreserveAspectCrop
                                sourceSize.width: 160
                                asynchronous: true
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                visible: !root.isImage(modelData)
                                Kirigami.Icon {
                                    Layout.preferredWidth: 28; Layout.preferredHeight: 28
                                    source: "mail-attachment-symbolic"
                                    color: Theme.secondary; isMask: true
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: root.fileName(modelData)
                                    elide: Text.ElideMiddle
                                    color: Theme.text
                                    font.pointSize: Theme.fontSize * 0.9
                                }
                            }
                        }
                        // remove
                        Rectangle {
                            anchors.top: parent.top; anchors.right: parent.right
                            width: 20; height: 20; radius: 10
                            color: Theme.secondary
                            Kirigami.Icon {
                                anchors.centerIn: parent
                                width: 12; height: 12
                                source: "window-close-symbolic"
                                color: Theme.windowBg; isMask: true
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.removePending(index)
                            }
                        }
                    }
                }
            }
        }

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
                visible: root.canAttach
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
                        // Ctrl+V with a copied image or file attaches it; text pastes as usual
                        Keys.onPressed: (event) => {
                            if (event.matches(StandardKey.Paste) && root.canAttach) {
                                const files = phone.clipboardFiles()
                                if (files.length > 0) { root.addPending(files); event.accepted = true }
                            }
                        }
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
                enabled: (composer.text.trim() !== "" || (root.pending.length > 0 && root.canAttach))
                         && (root.hasThread || to.text.trim() !== "")
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
        enabled: root.canAttach
        onDropped: (d) => { if (d.hasUrls) phone.sendFilesToThread(d.urls) }
    }

    function send() {
        const text = composer.text.trim()
        if (root.pending.length > 0 && root.canAttach) {
            phone.sendFilesToThread(root.pending)
            root.pending = []
        }
        if (!text) { composer.clear(); return }
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
