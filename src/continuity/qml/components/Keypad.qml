import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

GridLayout {
    id: root
    signal pressed(string key)
    columns: 3
    rowSpacing: 14
    columnSpacing: 22

    Repeater {
        model: [["1", ""], ["2", "ABC"], ["3", "DEF"], ["4", "GHI"], ["5", "JKL"], ["6", "MNO"],
                ["7", "PQRS"], ["8", "TUV"], ["9", "WXYZ"], ["*", ""], ["0", "+"], ["#", ""]]
        delegate: AbstractButton {
            id: key
            implicitWidth: 64
            implicitHeight: 64
            hoverEnabled: true
            background: Rectangle {
                radius: width / 2
                color: key.down ? Theme.selected : key.hovered ? Qt.darker(Theme.fieldBg, 1.0) : Theme.fieldBg
                Behavior on color { ColorAnimation { duration: 90 } }
            }
            contentItem: Column {
                anchors.centerIn: parent
                spacing: -2
                Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: modelData[0]
                    color: Theme.text
                    font.pointSize: Theme.fontSize * 1.7
                }
                Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: modelData[1]
                    color: Theme.secondary
                    font.pointSize: Theme.fontSize * 0.62
                    font.letterSpacing: 1.5
                    font.weight: Font.DemiBold
                }
            }
            onClicked: root.pressed(modelData[0])
            onPressAndHold: if (modelData[0] === "0") root.pressed("+")
        }
    }
}
