import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts

// Floating call card (like the macOS incoming-call banner / in-call HUD).
Item {
    id: root
    visible: opacity > 0
    opacity: phone.callState !== "" ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 200 } }
    width: 400
    height: card.height

    readonly property bool ringing: phone.callState === "ringing"
    readonly property bool active: phone.callState === "active"

    MultiEffect {
        source: card
        anchors.fill: card
        shadowEnabled: true
        shadowBlur: 1.0
        shadowColor: Theme.shadow
        shadowVerticalOffset: 6
    }

    Rectangle {
        id: card
        width: parent.width
        height: 82
        radius: 20
        color: Theme.dark ? "#2c2c2e" : "#ffffff"
        border.color: Theme.separator

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 14
            spacing: 12

            Avatar {
                size: 48
                source: phone.callAvatar
                initials: phone.callName && !/^[+\d]/.test(phone.callName)
                          ? phone.callName.split(" ").map(s => s[0]).join("").slice(0, 2).toUpperCase() : ""
                color: "#8e8e93"
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Label {
                    Layout.fillWidth: true
                    text: phone.callName
                    font.weight: Font.DemiBold
                    font.pointSize: Theme.fontSize * 1.1
                    color: Theme.text
                    elide: Text.ElideRight
                }
                Label {
                    text: root.ringing ? qsTr("Incoming call…")
                        : root.active ? phone.callDuration
                        : phone.callState === "dialing" || phone.callState === "alerting" ? qsTr("Calling…")
                        : phone.callState === "held" ? qsTr("On hold") : ""
                    color: Theme.secondary
                    font.features: { "tnum": 1 }
                }
            }

            IconButton {
                visible: !root.ringing
                size: 40
                iconName: phone.callMuted ? "microphone-sensitivity-muted-symbolic" : "microphone-sensitivity-high-symbolic"
                filled: true
                fill: phone.callMuted ? Theme.orange : (Theme.dark ? "#48484a" : "#d1d1d6")
                tip: phone.callMuted ? qsTr("Unmute") : qsTr("Mute")
                onClicked: phone.toggleMute()
            }
            IconButton {
                size: 40
                iconName: "call-stop-symbolic"
                filled: true
                fill: Theme.red
                tip: root.ringing ? qsTr("Decline") : qsTr("End")
                onClicked: root.ringing ? phone.decline() : phone.hangup()
            }
            IconButton {
                visible: root.ringing
                size: 40
                iconName: "call-start-symbolic"
                filled: true
                fill: Theme.green
                tip: qsTr("Answer")
                onClicked: phone.answer()
            }
        }
    }
}
