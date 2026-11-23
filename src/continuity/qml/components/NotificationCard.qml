import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    implicitHeight: col.implicitHeight + 24
    radius: 14
    color: Theme.cardBg
    border.color: Theme.separator
    border.width: 1
    property bool replying: false
    property bool showApp: true   // false inside an app group (the group header names the app)

    HoverHandler { id: hover }

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        anchors.leftMargin: 14
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            visible: root.showApp
            spacing: 8
            Item {
                Layout.preferredWidth: 20; Layout.preferredHeight: 20
                Image {
                    id: appIcon
                    anchors.fill: parent
                    source: model.icon
                    sourceSize: Qt.size(40, 40)
                    visible: status === Image.Ready
                }
                Kirigami.Icon {
                    anchors.fill: parent
                    visible: !appIcon.visible
                    source: "smartphone-symbolic"
                    color: Theme.secondary; isMask: true
                }
            }
            Label {
                Layout.fillWidth: true
                text: model.app.toUpperCase()
                color: Theme.secondary
                font.pointSize: Theme.fontSize * 0.78
                font.weight: Font.DemiBold
                font.letterSpacing: 0.5
                elide: Text.ElideRight
            }
            IconButton {
                size: 24
                iconName: "window-close-symbolic"
                tip: qsTr("Dismiss on phone")
                visible: model.dismissable
                opacity: hover.hovered ? 1 : 0.35
                onClicked: phone.dismiss(model.nid)
            }
        }

        Label {
            Layout.fillWidth: true
            Layout.rightMargin: root.showApp ? 0 : 22
            visible: model.title !== ""
            text: model.title
            font.weight: Font.DemiBold
            color: Theme.text
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
        }
        Label {
            Layout.fillWidth: true
            visible: model.text !== ""
            text: model.text
            color: Theme.text
            opacity: 0.85
            wrapMode: Text.Wrap
            maximumLineCount: 6
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            visible: model.canReply || model.canDelete
            spacing: 8
            Item { Layout.fillWidth: true; visible: !root.replying }
            Button {   // an email: delete it on the phone (Gmail's notification button)
                visible: model.canDelete && !root.replying
                text: qsTr("Delete")
                flat: true
                onClicked: phone.deleteNotificationItem(model.nid)
            }
            TextField {
                id: reply
                Layout.fillWidth: true
                visible: root.replying
                placeholderText: qsTr("Reply…")
                color: Theme.text
                onAccepted: { phone.replyNotification(model.nid, text); clear(); root.replying = false }
                Keys.onEscapePressed: root.replying = false
            }
            Button {
                visible: model.canReply
                text: root.replying ? qsTr("Send") : qsTr("Reply")
                flat: !root.replying
                onClicked: {
                    if (!root.replying) { root.replying = true; reply.forceActiveFocus() }
                    else { reply.accepted() }
                }
            }
        }
    }

    // dismiss when the app header row is hidden
    IconButton {
        visible: !root.showApp && model.dismissable
        anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 8
        size: 24
        iconName: "window-close-symbolic"
        tip: qsTr("Dismiss on phone")
        opacity: hover.hovered ? 1 : 0.35
        onClicked: phone.dismiss(model.nid)
    }
}
