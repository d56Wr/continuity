import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property int level: 0
    property bool charging: false
    property bool showText: true
    spacing: 3
    Item {
        implicitWidth: 21; implicitHeight: 10
        Rectangle {
            width: 18; height: 10; radius: 2.5
            color: "transparent"
            border.color: Theme.secondary
            border.width: 1
            Rectangle {
                x: 1.5; y: 1.5
                height: parent.height - 3
                width: Math.max(1, (parent.width - 3) * Math.min(100, root.level) / 100)
                radius: 1.5
                color: root.charging ? Theme.green : root.level <= 15 ? Theme.red : Theme.secondary
            }
        }
        Rectangle { x: 18.5; y: 3; width: 1.5; height: 4; radius: 1; color: Theme.secondary }
    }
    Label {
        visible: root.showText
        text: root.level + " %"
        color: Theme.secondary
        font.pointSize: Theme.fontSize * 0.85
    }
}
