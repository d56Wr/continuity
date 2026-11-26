import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ItemDelegate {
    id: root
    property bool selected: false
    height: 68
    padding: 0
    hoverEnabled: true

    background: Rectangle {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        radius: 9
        color: root.selected ? Theme.accent : root.hovered ? Theme.hover : "transparent"
    }

    contentItem: RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 18
        spacing: 10

        Rectangle {
            Layout.preferredWidth: 8; Layout.preferredHeight: 8; radius: 4
            color: model.unread ? (root.selected ? "white" : Theme.accent) : "transparent"
        }
        Avatar {
            size: 42
            source: model.avatar
            initials: model.initials
            color: model.color
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            RowLayout {
                Layout.fillWidth: true
                Label {
                    Layout.fillWidth: true
                    text: model.title
                    elide: Text.ElideRight
                    font.weight: Font.DemiBold
                    color: root.selected ? "white" : Theme.text
                }
                Label {
                    text: model.time
                    color: root.selected ? Qt.rgba(1, 1, 1, 0.8) : Theme.secondary
                    font.pointSize: Theme.fontSize * 0.85
                }
            }
            Label {
                Layout.fillWidth: true
                text: model.snippet
                maximumLineCount: 2
                wrapMode: Text.Wrap
                elide: Text.ElideRight
                color: root.selected ? Qt.rgba(1, 1, 1, 0.85) : Theme.secondary
                font.pointSize: Theme.fontSize * 0.92
                textFormat: Text.PlainText
            }
        }
    }

    // right-click: pin, mark as read / unread (like Messages on macOS)
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: menu.popup()
    }
    Menu {
        id: menu
        MenuItem {
            text: model.pinned ? qsTr("Unpin") : qsTr("Pin")
            icon.name: model.pinned ? "window-unpin" : "window-pin"
            onTriggered: model.pinned ? phone.unpinThread(model.threadId) : phone.pinThread(model.threadId)
        }
        MenuItem {
            text: model.unread ? qsTr("Mark as Read") : qsTr("Mark as Unread")
            onTriggered: model.unread ? phone.markRead(model.threadId) : phone.markUnread(model.threadId)
        }
    }
}
