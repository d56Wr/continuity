import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property int strength: 0   // 0..4
    property string type: ""
    spacing: 4
    Row {
        spacing: 1.5
        Layout.alignment: Qt.AlignVCenter
        Repeater {
            model: 4
            Rectangle {
                width: 3
                height: 4 + index * 2.5
                anchors.bottom: parent.bottom
                radius: 1
                color: index < root.strength ? Theme.secondary : Theme.separator
            }
        }
    }
    Label {
        text: root.type
        color: Theme.secondary
        font.pointSize: Theme.fontSize * 0.8
        font.weight: Font.DemiBold
    }
}
