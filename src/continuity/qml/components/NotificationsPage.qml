import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: qsTr("Notifications")
                font.pointSize: Theme.fontSize * 1.7
                font.weight: Font.Bold
                color: Theme.text
                Layout.fillWidth: true
            }
            Button {
                text: qsTr("Clear All")
                visible: list.count > 0
                flat: true
                onClicked: phone.dismissAll()
            }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: 720
            Layout.alignment: Qt.AlignHCenter
            clip: true
            spacing: 10
            model: phone.notifications
            ScrollBar.vertical: ScrollBar {}

            add: Transition { NumberAnimation { properties: "opacity"; from: 0; to: 1; duration: 180 } }
            remove: Transition {
                ParallelAnimation {
                    NumberAnimation { property: "opacity"; to: 0; duration: 180 }
                    NumberAnimation { property: "x"; to: 60; duration: 180 }
                }
            }
            displaced: Transition { NumberAnimation { properties: "y"; duration: 180; easing.type: Easing.OutCubic } }

            delegate: NotificationCard { width: list.width }

            ColumnLayout {
                anchors.centerIn: parent
                visible: list.count === 0
                spacing: 10
                Kirigami.Icon {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 64; Layout.preferredHeight: 64
                    source: "notifications-disabled-symbolic"
                    color: Theme.tertiary; isMask: true
                }
                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("No notifications")
                    color: Theme.secondary
                    font.pointSize: Theme.fontSize * 1.2
                }
            }
        }
    }
}
