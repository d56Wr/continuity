import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Rectangle {
    color: Qt.rgba(Theme.windowBg.r, Theme.windowBg.g, Theme.windowBg.b, 0.92)
    MouseArea { anchors.fill: parent; hoverEnabled: true }  // block clicks below

    ColumnLayout {
        anchors.centerIn: parent
        width: 420
        spacing: 12
        Kirigami.Icon {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 72; Layout.preferredHeight: 72
            source: "smartphone-disconnected"
            fallback: "smartphone-symbolic"
            color: Theme.tertiary
        }
        Label {
            Layout.alignment: Qt.AlignHCenter
            text: !phone.daemonAvailable ? qsTr("KDE Connect is not running")
                : !phone.paired ? qsTr("No phone paired")
                : qsTr("%1 is not reachable").arg(phone.deviceName)
            font.pointSize: Theme.fontSize * 1.4
            font.weight: Font.DemiBold
            color: Theme.text
        }
        Label {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            color: Theme.secondary
            text: !phone.paired
                  ? qsTr("Install KDE Connect on your Android phone, connect it to the same network and pair it with this computer.")
                  : qsTr("Make sure the phone is on the same network and the KDE Connect app is allowed to run in the background.")
        }
    }
}
