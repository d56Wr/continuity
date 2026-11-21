import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    implicitHeight: col.implicitHeight + (model.groupEnd ? 8 : 2)

    readonly property bool out: model.outgoing
    readonly property var images: model.images
    readonly property real maxBubble: Math.min(520, width * 0.68)
    // like iMessage: RCS (chat) bubbles are blue, plain SMS/MMS green
    readonly property color outColor: phone.messageSource === "google" && !phone.threadIsRcs ? Theme.green : Theme.bubbleOut

    ColumnLayout {
        id: col
        width: parent.width
        spacing: 2

        Label {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 10
            Layout.bottomMargin: 6
            visible: model.showDay
            text: model.dayLabel
            color: Theme.secondary
            font.pointSize: Theme.fontSize * 0.82
            font.weight: Font.DemiBold
        }

        // sender name in group chats
        Label {
            Layout.leftMargin: 30
            Layout.topMargin: 4
            visible: !!model.showSender
            text: model.sender || ""
            color: Theme.secondary
            font.pointSize: Theme.fontSize * 0.8
        }

        // images (thumbnails)
        Repeater {
            model: root.images
            delegate: Image {
                Layout.alignment: root.out ? Qt.AlignRight : Qt.AlignLeft
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                source: modelData
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                Layout.maximumWidth: 280
                Layout.preferredWidth: Math.min(280, implicitWidth)
                Layout.preferredHeight: Math.min(280, implicitWidth) * implicitHeight / Math.max(1, implicitWidth)
                smooth: true
                TapHandler { onTapped: Qt.openUrlExternally(parent.source) }
            }
        }

        Rectangle {
            id: bubble
            visible: model.body !== "" || model.attachmentCount > root.images.length
            Layout.alignment: root.out ? Qt.AlignRight : Qt.AlignLeft
            Layout.leftMargin: 18
            Layout.rightMargin: 18
            Layout.topMargin: (model.reactions || "") !== "" ? 12 : 0
            implicitWidth: Math.min(root.maxBubble, body.implicitWidth + 26)
            implicitHeight: body.implicitHeight + 14
            radius: 17
            color: model.status === "failed" ? Theme.red : root.out ? root.outColor : Theme.bubbleIn
            opacity: model.status === "sending" ? 0.6 : 1

            TextEdit {
                id: body
                anchors.left: parent.left
                anchors.leftMargin: 13
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(root.maxBubble - 26, implicitWidth)
                text: model.body !== "" ? model.body : qsTr("Attachment")
                wrapMode: Text.Wrap
                readOnly: true
                selectByMouse: true
                color: root.out || model.status === "failed" ? "white" : Theme.text
                selectedTextColor: "white"
                selectionColor: Qt.darker(Theme.accent, 1.3)
                textFormat: TextEdit.PlainText
                font.pointSize: Theme.fontSize * 1.02
            }

            // reactions badge (tapback-style), on the top corner of the bubble
            Rectangle {
                visible: (model.reactions || "") !== ""
                anchors.top: parent.top
                anchors.topMargin: -12
                x: root.out ? -width + 14 : parent.width - 14
                height: 24
                width: reactionText.implicitWidth + 14
                radius: 12
                color: Theme.dark ? "#3a3a3c" : "#ffffff"
                border.color: Theme.windowBg
                border.width: 2
                Label { id: reactionText; anchors.centerIn: parent; text: model.reactions || "" }
            }

            ToolTip.visible: hover.hovered
            ToolTip.delay: 700
            ToolTip.text: model.time
            HoverHandler { id: hover }
            TapHandler {
                acceptedButtons: Qt.RightButton
                onTapped: menu.popup()
            }
            Menu {
                id: menu
                MenuItem { text: qsTr("Copy"); onTriggered: phone.copyText(model.body) }
                MenuSeparator { visible: phone.messageSource === "google" }
                Repeater {
                    model: phone.messageSource === "google" ? ["❤️", "👍", "😂", "😮", "😢", "👎"] : []
                    MenuItem { text: modelData; onTriggered: phone.react(root.uid, modelData) }
                }
            }
        }

        Label {
            Layout.alignment: root.out ? Qt.AlignRight : Qt.AlignLeft
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            Layout.topMargin: (model.reactions || "") !== "" ? 2 : 0
            visible: model.status === "failed" || model.status === "sending" || (model.receipt || "") !== ""
                     || (model.groupEnd && root.out && phone.messageSource !== "google")
            text: model.status === "failed" ? qsTr("Not delivered")
                : model.status === "sending" ? qsTr("Sending…")
                : (model.receipt || "") !== "" ? model.receipt : model.time
            color: model.status === "failed" ? Theme.red : Theme.tertiary
            font.pointSize: Theme.fontSize * 0.78
        }
    }

    readonly property string uid: model.uid
}
