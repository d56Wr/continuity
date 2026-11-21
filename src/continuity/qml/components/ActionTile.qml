import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

AbstractButton {
    id: root
    property string iconName
    property string title
    property string subtitle
    Layout.fillWidth: true
    implicitHeight: 86
    hoverEnabled: true
    enabled: phone.connected
    opacity: enabled ? 1 : 0.5

    background: Rectangle {
        radius: 14
        color: root.down ? Theme.selected : root.hovered ? Theme.hover : Theme.cardBg
        border.color: Theme.separator
    }
    padding: 14
    contentItem: ColumnLayout {
        spacing: 2
        Kirigami.Icon {
            Layout.preferredWidth: 22; Layout.preferredHeight: 22
            Layout.bottomMargin: 6
            source: root.iconName; color: Theme.accent; isMask: true
        }
        Label {
            text: root.title; color: Theme.text; font.weight: Font.DemiBold
        }
        Label {
            text: root.subtitle; color: Theme.secondary; font.pointSize: Theme.fontSize * 0.85
        }
        Item { Layout.fillHeight: true }
    }
}
