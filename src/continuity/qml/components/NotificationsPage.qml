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
            objectName: "notificationList"
            Kirigami.WheelHandler { target: list; filterMouseEvents: true; keyNavigationEnabled: true }
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: 720
            Layout.alignment: Qt.AlignHCenter
            clip: true
            spacing: 0
            model: phone.notifications
            ScrollBar.vertical: ScrollBar {}

            // apps whose group is expanded (groups start collapsed, like on the phone)
            property var expanded: ({})
            function toggle(app) {
                const e = Object.assign({}, expanded)
                if (e[app]) delete e[app]; else e[app] = true
                expanded = e
            }

            displaced: Transition { NumberAnimation { properties: "y"; duration: 180; easing.type: Easing.OutCubic } }

            delegate: Item {
                id: entry
                width: list.width
                readonly property bool open: !!list.expanded[model.app] || model.groupCount === 1
                readonly property bool shown: open || model.groupIndex === 0
                readonly property bool stacked: !open && model.groupIndex === 0
                readonly property int groupCount: model.groupCount
                height: shown ? col.implicitHeight : 0
                visible: shown
                Behavior on height { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

                Column {
                    id: col
                    width: parent.width
                    spacing: 6
                    topPadding: model.groupIndex === 0 ? 10 : 0
                    bottomPadding: entry.stacked && model.groupCount > 1 ? 18 : 10

                    // group header: app, count, expand / collapse, clear the group
                    RowLayout {
                        visible: model.groupIndex === 0
                        width: parent.width
                        spacing: 8
                        Item {
                            Layout.preferredWidth: 18; Layout.preferredHeight: 18
                            Image {
                                id: groupIcon
                                anchors.fill: parent
                                source: model.icon
                                sourceSize: Qt.size(36, 36)
                                visible: status === Image.Ready
                            }
                            Kirigami.Icon {
                                anchors.fill: parent
                                visible: !groupIcon.visible
                                source: "smartphone-symbolic"
                                color: Theme.secondary; isMask: true
                            }
                        }
                        Label {
                            text: model.app
                            color: Theme.text
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            Layout.maximumWidth: list.width * 0.6
                        }
                        Rectangle {
                            visible: model.groupCount > 1
                            radius: height / 2
                            color: Theme.fieldBg
                            implicitWidth: countLabel.implicitWidth + 12
                            implicitHeight: countLabel.implicitHeight + 2
                            Label {
                                id: countLabel
                                anchors.centerIn: parent
                                text: model.groupCount
                                color: Theme.secondary
                                font.pointSize: Theme.fontSize * 0.85
                            }
                        }
                        Item { Layout.fillWidth: true }
                        IconButton {
                            visible: model.groupCount > 1
                            size: 26
                            iconName: entry.open ? "go-up-symbolic" : "go-down-symbolic"
                            tip: entry.open ? qsTr("Collapse") : qsTr("Expand")
                            onClicked: list.toggle(model.app)
                        }
                        IconButton {
                            visible: model.groupDismissable
                            size: 26
                            iconName: "edit-clear-all-symbolic"
                            tip: model.groupCount > 1 ? qsTr("Clear all from %1").arg(model.app) : qsTr("Dismiss on phone")
                            onClicked: phone.dismissGroup(model.app)
                        }
                    }

                    Item {
                        width: parent.width
                        height: card.height
                        // collapsed group: the other notifications peek out below, like a stack
                        Repeater {
                            model: entry.stacked ? Math.min(2, entry.groupCount - 1) : 0
                            Rectangle {
                                required property int index
                                z: -1 - index
                                x: 12 * (index + 1)
                                width: parent.width - 24 * (index + 1)
                                y: 7 * (index + 1)
                                height: card.height
                                radius: 14
                                color: Theme.cardBg
                                border.color: Theme.separator
                                opacity: 0.75 - index * 0.25
                            }
                        }
                        NotificationCard {
                            id: card
                            width: parent.width
                            showApp: false
                        }
                        MouseArea {   // tap a collapsed stack to open it (buttons still work above)
                            anchors.fill: card
                            z: -1
                            enabled: entry.stacked && model.groupCount > 1
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: list.toggle(model.app)
                        }
                    }
                }
            }

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
