import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    implicitHeight: col.implicitHeight + (model.groupEnd ? 8 : 2)

    readonly property bool out: model.outgoing
    readonly property var images: model.images
    readonly property real maxBubble: Math.min(520, width * 0.68)

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

        // images (thumbnails from the phone)
        Repeater {
            model: root.images
            delegate: Image {
                Layout.alignment: root.out ? Qt.AlignRight : Qt.AlignLeft
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                source: modelData
                fillMode: Image.PreserveAspectFit
                Layout.maximumWidth: 260
                Layout.preferredWidth: Math.min(260, implicitWidth)
                Layout.preferredHeight: Math.min(260, implicitWidth) * implicitHeight / Math.max(1, implicitWidth)
                smooth: true
            }
        }

        Rectangle {
            id: bubble
            visible: model.body !== "" || model.attachmentCount > root.images.length
            Layout.alignment: root.out ? Qt.AlignRight : Qt.AlignLeft
            Layout.leftMargin: 18
            Layout.rightMargin: 18
            implicitWidth: Math.min(root.maxBubble, body.implicitWidth + 26)
            implicitHeight: body.implicitHeight + 14
            radius: 17
            color: model.status === "failed" ? Theme.red : root.out ? Theme.bubbleOut : Theme.bubbleIn
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
            }
        }

        Label {
            Layout.alignment: root.out ? Qt.AlignRight : Qt.AlignLeft
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            visible: model.groupEnd && (model.status !== "" || root.out)
            text: model.status === "failed" ? qsTr("Not delivered") : model.status === "sending" ? qsTr("Sending…") : model.time
            color: model.status === "failed" ? Theme.red : Theme.tertiary
            font.pointSize: Theme.fontSize * 0.78
        }
    }
}
