import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    color: Theme.sidebarBg
    property int current: 0
    signal selected(int index)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        anchors.topMargin: 16
        spacing: 4

        // device card
        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 14
            spacing: 10
            Rectangle {
                Layout.preferredWidth: 38; Layout.preferredHeight: 38; radius: 10
                gradient: Gradient {
                    GradientStop { position: 0; color: "#5ac8fa" }
                    GradientStop { position: 1; color: "#0a64e6" }
                }
                Kirigami.Icon {
                    anchors.centerIn: parent
                    width: 22; height: 22
                    source: "smartphone-symbolic"
                    color: "white"; isMask: true
                }
            }
            ColumnLayout {
                spacing: 1
                Layout.fillWidth: true
                Label {
                    Layout.fillWidth: true
                    text: phone.deviceName || qsTr("No phone")
                    font.weight: Font.DemiBold
                    color: Theme.text
                    elide: Text.ElideRight
                }
                RowLayout {
                    spacing: 5
                    Rectangle {
                        Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 3.5
                        color: phone.connected ? Theme.green : Theme.tertiary
                    }
                    Label {
                        text: phone.connected ? qsTr("Connected") : qsTr("Not connected")
                        color: Theme.secondary
                        font.pointSize: Theme.fontSize * 0.88
                    }
                    BatteryIndicator {
                        visible: phone.connected && phone.battery >= 0
                        level: phone.battery
                        charging: phone.charging
                    }
                }
            }
        }

        NavItem {
            iconName: "mail-message-new-symbolic"; text: qsTr("Messages")
            badge: phone.unreadCount
            active: root.current === 0; onClicked: root.selected(0)
        }
        NavItem {
            iconName: "call-start-symbolic"; text: qsTr("Calls")
            active: root.current === 1; onClicked: root.selected(1)
            badge: phone.callState === "ringing" ? 1 : 0
        }
        NavItem {
            iconName: "notifications-symbolic"; text: qsTr("Notifications")
            badge: phone.notifications.count
            badgeMuted: true
            active: root.current === 2; onClicked: root.selected(2)
        }
        NavItem {
            iconName: "smartphone-symbolic"; text: qsTr("Phone")
            active: root.current === 3; onClicked: root.selected(3)
        }

        Item { Layout.fillHeight: true }

        // quick actions
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            IconButton {
                iconName: "find-location-symbolic"; tip: qsTr("Find my phone")
                enabled: phone.connected; onClicked: phone.ring()
            }
            IconButton {
                iconName: "edit-paste-symbolic"; tip: qsTr("Send clipboard to phone")
                enabled: phone.connected; onClicked: phone.sendClipboard()
            }
            IconButton {
                iconName: "folder-symbolic"; tip: qsTr("Browse phone files")
                enabled: phone.connected; onClicked: phone.browseFiles()
            }
            Item { Layout.fillWidth: true }
            NetworkIndicator {
                visible: phone.connected && phone.networkStrength >= 0
                strength: phone.networkStrength
                type: phone.networkType
            }
        }
    }
}
