import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 24
    width: label.implicitWidth + 32
    height: 36
    radius: 18
    color: Theme.dark ? "#3a3a3c" : "#1d1d1f"
    opacity: 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 180 } }

    function show(text) {
        label.text = text
        opacity = 0.96
        timer.restart()
    }
    Label { id: label; anchors.centerIn: parent; color: "white" }
    Timer { id: timer; interval: 2600; onTriggered: root.opacity = 0 }
}
