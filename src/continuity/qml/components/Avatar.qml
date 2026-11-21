import QtQuick
import QtQuick.Effects
import org.kde.kirigami as Kirigami

Item {
    id: root
    property string source: ""
    property string initials: ""
    property color color: "#8e8e93"
    property int size: 40
    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        visible: img.status !== Image.Ready
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.lighter(root.color, 1.2) }
            GradientStop { position: 1; color: Qt.darker(root.color, 1.15) }
        }
        Text {
            anchors.centerIn: parent
            visible: root.initials !== ""
            text: root.initials
            color: "white"
            font.pixelSize: root.size * (root.initials.length > 1 ? 0.38 : 0.44)
            font.weight: Font.DemiBold
        }
        Kirigami.Icon {
            anchors.centerIn: parent
            visible: root.initials === ""
            width: root.size * 0.56
            height: width
            source: "user-symbolic"
            color: "white"
            isMask: true
        }
    }

    Image {
        id: img
        anchors.fill: parent
        source: root.source
        sourceSize: Qt.size(root.size * 2, root.size * 2)
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        visible: false
    }
    Item {
        id: mask
        anchors.fill: parent
        layer.enabled: true
        visible: false
        Rectangle { anchors.fill: parent; radius: width / 2; color: "black" }
    }
    MultiEffect {
        anchors.fill: parent
        source: img
        maskEnabled: true
        maskSource: mask
        visible: img.status === Image.Ready
    }
}
