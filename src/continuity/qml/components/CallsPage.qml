import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root
    signal messageNumber(string number)

    function dialNumber(n) { number.text = n; phone.dial(n) }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---------------------------------------------------------- contacts
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 340
            color: Theme.panelBg
            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                SearchBox {
                    id: search
                    Layout.fillWidth: true
                    Layout.margins: 12
                    hint: qsTr("Search contacts")
                    onTextChanged: phone.filterContacts(text)
                    Component.onCompleted: phone.filterContacts("")
                }
                ListView {
                    id: contacts
                    Kirigami.WheelHandler { target: contacts; filterMouseEvents: true; keyNavigationEnabled: true }
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: phone.contacts
                    reuseItems: true
                    ScrollBar.vertical: ScrollBar {}
                    section.property: "name"
                    section.criteria: ViewSection.FirstCharacter
                    section.delegate: Label {
                        leftPadding: 18; topPadding: 8; bottomPadding: 2
                        text: section
                        color: Theme.secondary
                        font.weight: Font.DemiBold
                        font.pointSize: Theme.fontSize * 0.85
                    }
                    delegate: ItemDelegate {
                        id: d
                        width: contacts.width
                        height: 52
                        hoverEnabled: true
                        background: Rectangle {
                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
                            radius: 8; color: d.hovered ? Theme.hover : "transparent"
                        }
                        contentItem: RowLayout {
                            spacing: 10
                            Item { Layout.preferredWidth: 4 }
                            Avatar { size: 34; source: model.avatar; initials: model.initials; color: model.color }
                            ColumnLayout {
                                spacing: 0
                                Layout.fillWidth: true
                                Label { text: model.name; color: Theme.text; elide: Text.ElideRight; Layout.fillWidth: true }
                                Label { text: model.number; color: Theme.secondary; font.pointSize: Theme.fontSize * 0.85 }
                            }
                            IconButton {
                                iconName: "mail-message-new-symbolic"; tip: qsTr("Message"); tint: Theme.accent
                                visible: d.hovered
                                onClicked: root.messageNumber(model.number)
                            }
                            IconButton {
                                iconName: "call-start-symbolic"; tip: qsTr("Call"); tint: Theme.green
                                enabled: phone.callsAvailable
                                onClicked: root.dialNumber(model.number)
                            }
                        }
                        onDoubleClicked: root.dialNumber(model.number)
                    }
                    Label {
                        anchors.centerIn: parent
                        width: parent.width - 40
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        visible: contacts.count === 0
                        text: phone.contactCount === 0
                              ? qsTr("No contacts. Enable “Contacts synchronizer” in the KDE Connect app on your phone.")
                              : qsTr("No results")
                        color: Theme.secondary
                    }
                }
            }
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: Theme.separator }

        // ---------------------------------------------------------- keypad
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 18
                width: 280

                TextField {
                    id: number
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    font.pointSize: Theme.fontSize * 2
                    color: Theme.text
                    placeholderText: qsTr("Phone number")
                    placeholderTextColor: Theme.tertiary
                    background: null
                    inputMethodHints: Qt.ImhDialableCharactersOnly
                    Keys.onReturnPressed: phone.dial(text)
                }

                Keypad {
                    Layout.alignment: Qt.AlignHCenter
                    onPressed: (key) => {
                        if (phone.callState === "active") phone.sendTones(key)
                        number.insert(number.cursorPosition, key)
                    }
                }

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 24
                    Item { Layout.preferredWidth: 44 }
                    IconButton {
                        size: 64
                        iconName: "call-start-symbolic"
                        filled: true
                        fill: Theme.green
                        iconScale: 0.45
                        enabled: phone.callsAvailable && number.text.length > 0 && phone.callState === ""
                        tip: qsTr("Call")
                        onClicked: phone.dial(number.text)
                    }
                    IconButton {
                        size: 44
                        iconName: "edit-clear-symbolic"
                        tip: qsTr("Delete")
                        opacity: number.text ? 1 : 0
                        onClicked: number.remove(number.text.length - 1, number.text.length)
                        onPressAndHold: number.clear()
                    }
                }

                Label {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    visible: !phone.callsAvailable
                    text: qsTr("Calls need the phone connected over Bluetooth as a hands-free device.")
                    color: Theme.secondary
                }
            }
        }
    }
}
