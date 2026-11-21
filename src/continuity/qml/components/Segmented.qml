import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// macOS-style segmented control
Rectangle {
    id: root
    property var model: []
    property int currentIndex: 0
    signal activated(int index)

    implicitHeight: 28
    radius: 8
    color: Theme.fieldBg

    Rectangle {
        id: thumb
        y: 2
        height: parent.height - 4
        width: (root.width - 4) / Math.max(1, root.model.length)
        x: 2 + root.currentIndex * width
        radius: 6
        color: Theme.dark ? "#5a5a5e" : "#ffffff"
        Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 2
        spacing: 0
        Repeater {
            model: root.model
            delegate: Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Label {
                    anchors.centerIn: parent
                    text: modelData
                    color: Theme.text
                    font.weight: index === root.currentIndex ? Font.DemiBold : Font.Normal
                    font.pointSize: Theme.fontSize * 0.92
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: { root.currentIndex = index; root.activated(index) }
                }
            }
        }
    }
}
