import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    property string iconName
    property string text
    property bool active: false
    property int badge: 0
    property bool badgeMuted: false
    signal clicked()

    Layout.fillWidth: true
    implicitHeight: 34
    radius: 8
    color: active ? Theme.selected : mouse.containsMouse ? Theme.hover : "transparent"

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 8
        spacing: 10
        Kirigami.Icon {
            Layout.preferredWidth: 18; Layout.preferredHeight: 18
            source: root.iconName
            color: root.active ? Theme.accent : Theme.secondary
            isMask: true
        }
        Label {
            Layout.fillWidth: true
            text: root.text
            color: Theme.text
            font.weight: root.active ? Font.DemiBold : Font.Normal
        }
        Rectangle {
            visible: root.badge > 0
            implicitWidth: Math.max(20, badgeText.implicitWidth + 12)
            implicitHeight: 18
            radius: 9
            color: root.badgeMuted ? Theme.selected : Theme.red
            Label {
                id: badgeText
                anchors.centerIn: parent
                text: root.badge > 99 ? "99+" : root.badge
                color: root.badgeMuted ? Theme.secondary : "white"
                font.pointSize: Theme.fontSize * 0.8
                font.weight: Font.DemiBold
            }
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.clicked()
    }
}
