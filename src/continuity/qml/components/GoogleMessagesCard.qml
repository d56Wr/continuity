import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Pair / manage the native Google Messages connection (SMS + RCS in the Messages tab).
Rectangle {
    id: root
    implicitHeight: col.implicitHeight + 28
    radius: 14
    color: Theme.cardBg
    border.color: Theme.separator
    visible: phone.gmAvailable

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Rectangle {
                Layout.preferredWidth: 36; Layout.preferredHeight: 36; radius: 9
                gradient: Gradient {
                    GradientStop { position: 0; color: "#4c8bf5" }
                    GradientStop { position: 1; color: "#1a5fd1" }
                }
                Kirigami.Icon {
                    anchors.centerIn: parent; width: 20; height: 20
                    source: "dialog-messages"; color: "white"; isMask: true
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Label {
                    text: qsTr("Google Messages · SMS and RCS")
                    font.weight: Font.DemiBold
                    color: Theme.text
                }
                Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    color: Theme.secondary
                    font.pointSize: Theme.fontSize * 0.9
                    text: phone.gmQr !== "" ? qsTr("Waiting for the QR code to be scanned…")
                        : !phone.gmPaired ? qsTr("Pair to see RCS chats (including iPhones) with read receipts, reactions and full-size photos in Messages.")
                        : phone.gmInactive ? qsTr("Google Messages is open somewhere else.")
                        : phone.gmConnected ? qsTr("Connected — Messages shows SMS and RCS.")
                        : qsTr("Connecting…")
                }
            }
            Button {
                visible: !phone.gmPaired && phone.gmQr === ""
                text: qsTr("Pair with QR code")
                highlighted: true
                onClicked: phone.gmPair()
            }
            Button {
                visible: phone.gmPaired && phone.gmInactive
                text: qsTr("Use here")
                onClicked: phone.gmActivate()
            }
            Button {
                visible: phone.gmPaired
                text: qsTr("Unpair")
                flat: true
                onClicked: confirm.open()
            }
            Button {
                visible: phone.gmQr !== ""
                text: qsTr("Cancel")
                flat: true
                onClicked: phone.gmCancelPair()
            }
        }

        // QR code + instructions
        RowLayout {
            Layout.fillWidth: true
            visible: phone.gmQr !== ""
            spacing: 20
            Rectangle {
                Layout.preferredWidth: 220; Layout.preferredHeight: 220
                radius: 12; color: "white"
                Image {
                    anchors.fill: parent; anchors.margins: 6
                    source: phone.gmQr
                    cache: false
                    smooth: false
                    fillMode: Image.PreserveAspectFit
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: [
                        qsTr("1. On your phone open Google Messages."),
                        qsTr("2. Tap your profile picture → Device pairing."),
                        qsTr("3. Tap “QR code scanner” and point the phone at this code."),
                        qsTr("The code refreshes automatically.")
                    ]
                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: modelData
                        color: index === 3 ? Theme.secondary : Theme.text
                    }
                }
            }
        }
    }

    Dialog {
        id: confirm
        anchors.centerIn: Overlay.overlay
        modal: true
        title: qsTr("Unpair Google Messages?")
        standardButtons: Dialog.Yes | Dialog.No
        Label { text: qsTr("Messages will fall back to SMS from KDE Connect."); color: Theme.text }
        onAccepted: phone.gmUnpair()
    }
}
