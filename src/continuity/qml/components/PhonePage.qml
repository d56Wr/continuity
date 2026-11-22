import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Flickable {
    id: root
    Kirigami.WheelHandler { target: root; filterMouseEvents: true; keyNavigationEnabled: true }
    contentHeight: col.implicitHeight + 48
    clip: true
    ScrollBar.vertical: ScrollBar {}

    ColumnLayout {
        id: col
        x: 24
        y: 24
        width: Math.min(720, root.width - 48)
        spacing: 18

        // ---------------------------------------------------------- status card
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 120
            radius: 16
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "#0a64e6" }
                GradientStop { position: 1; color: "#5ac8fa" }
            }
            RowLayout {
                anchors.fill: parent
                anchors.margins: 22
                spacing: 18
                Kirigami.Icon {
                    Layout.preferredWidth: 54; Layout.preferredHeight: 54
                    source: "smartphone-symbolic"; color: "white"; isMask: true
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Label {
                        text: phone.deviceName || qsTr("No phone paired")
                        color: "white"
                        font.pointSize: Theme.fontSize * 1.6
                        font.weight: Font.Bold
                    }
                    Label {
                        color: Qt.rgba(1, 1, 1, 0.85)
                        text: phone.connected
                              ? qsTr("Battery %1 %%2 · %3 · %4 contacts")
                                  .arg(phone.battery).arg(phone.charging ? qsTr(" (charging)") : "")
                                  .arg(phone.networkType || qsTr("no signal")).arg(phone.contactCount)
                              : qsTr("Not connected")
                    }
                    Label {
                        color: Qt.rgba(1, 1, 1, 0.85)
                        text: phone.callsAvailable ? qsTr("Calls: connected over Bluetooth")
                                                   : qsTr("Calls: Bluetooth hands-free not connected")
                    }
                }
            }
        }

        // ---------------------------------------------------------- actions
        GridLayout {
            Layout.fillWidth: true
            columns: 3
            rowSpacing: 12
            columnSpacing: 12

            ActionTile {
                iconName: "find-location-symbolic"; title: qsTr("Find My Phone")
                subtitle: qsTr("Ring at full volume"); onClicked: phone.ring()
            }
            ActionTile {
                iconName: "document-send-symbolic"; title: qsTr("Send Files")
                subtitle: qsTr("Like AirDrop"); onClicked: fileDialog.open()
            }
            ActionTile {
                iconName: "folder-symbolic"; title: qsTr("Browse Files")
                subtitle: qsTr("Open phone storage"); onClicked: phone.browseFiles()
            }
            ActionTile {
                iconName: "edit-paste-symbolic"; title: qsTr("Send Clipboard")
                subtitle: qsTr("Paste it on the phone"); onClicked: phone.sendClipboard()
            }
            ActionTile {
                iconName: "view-refresh-symbolic"; title: qsTr("Sync Contacts")
                subtitle: qsTr("%n contact(s)", "", phone.contactCount); onClicked: phone.syncContacts()
            }
        }

        // what's playing on the phone
        Label {
            visible: phone.mediaAvailable
            text: qsTr("Now Playing on Phone")
            font.weight: Font.Bold
            font.pointSize: Theme.fontSize * 1.2
            color: Theme.text
            Layout.topMargin: 6
        }
        NowPlaying {
            visible: phone.mediaAvailable
            Layout.fillWidth: true
        }

        // drop zone
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 110
            radius: 14
            color: drop.containsDrag ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12) : "transparent"
            border.color: drop.containsDrag ? Theme.accent : Theme.separator
            border.width: 2
            Label {
                anchors.centerIn: parent
                text: qsTr("Drop files here to send them to your phone")
                color: drop.containsDrag ? Theme.accent : Theme.secondary
            }
            DropArea {
                id: drop
                anchors.fill: parent
                onDropped: (d) => { if (d.hasUrls) phone.sendFiles(d.urls) }
            }
        }

        GoogleMessagesCard { Layout.fillWidth: true }

        // ---------------------------------------------------------- settings
        Label {
            text: qsTr("Settings")
            font.weight: Font.Bold
            font.pointSize: Theme.fontSize * 1.2
            color: Theme.text
            Layout.topMargin: 6
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: settingsCol.implicitHeight + 16
            radius: 12
            color: Theme.cardBg
            border.color: Theme.separator
            ColumnLayout {
                id: settingsCol
                anchors.fill: parent
                anchors.margins: 8
                Switch {
                    Layout.fillWidth: true
                    enabled: phone.connected
                    text: qsTr("Share clipboard automatically")
                    checked: phone.clipboardAutoShare
                    onToggled: phone.clipboardAutoShare = checked
                }
                Label {
                    Layout.fillWidth: true
                    Layout.leftMargin: 6
                    Layout.rightMargin: 6
                    Layout.bottomMargin: 4
                    text: qsTr("Text you copy on this computer appears on the phone. Android doesn't let apps read the clipboard in the background, so to go the other way use \"Send clipboard\" in the KDE Connect notification or quick-settings tile on the phone.")
                    color: Theme.secondary
                    wrapMode: Text.Wrap
                    font.pointSize: Theme.fontSize * 0.85
                }
                Switch {
                    Layout.fillWidth: true
                    text: qsTr("Start at login (in the background)")
                    checked: phone.autostart
                    onToggled: phone.autostart = checked
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 6
                    Label { text: qsTr("Language"); color: Theme.text; Layout.fillWidth: true }
                    ComboBox {
                        id: lang
                        readonly property var codes: ["", "en", "cs"]
                        model: [qsTr("System"), "English", "Čeština"]
                        currentIndex: Math.max(0, codes.indexOf(phone.language))
                        onActivated: (i) => phone.language = codes[i]
                    }
                }
            }
        }

        Label {
            Layout.fillWidth: true
            text: qsTr("Continuity %1 · uses KDE Connect for messages and notifications, and Bluetooth hands-free (PipeWire) for calls.").arg(appVersion)
            color: Theme.tertiary
            wrapMode: Text.Wrap
            font.pointSize: Theme.fontSize * 0.85
        }
    }

    FileDialog {
        id: fileDialog
        fileMode: FileDialog.OpenFiles
        title: qsTr("Send files to phone")
        onAccepted: phone.sendFiles(selectedFiles)
    }
}
