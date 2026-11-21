import QtQuick
import QtQuick.Controls
import org.kde.kirigami as Kirigami

// Round, borderless icon button (macOS toolbar style). Set `filled` for a coloured circle.
AbstractButton {
    id: root
    property string iconName
    property string tip: ""
    property color tint: Theme.secondary
    property color fill: "transparent"
    property bool filled: false
    property int size: 30
    property real iconScale: 0.6

    implicitWidth: size
    implicitHeight: size
    hoverEnabled: true
    opacity: enabled ? 1 : 0.4
    focusPolicy: Qt.TabFocus

    background: Rectangle {
        radius: root.filled ? width / 2 : 8
        color: root.filled ? (root.down ? Qt.darker(root.fill, 1.2) : root.hovered ? Qt.lighter(root.fill, 1.1) : root.fill)
                           : (root.down ? Theme.selected : root.hovered ? Theme.hover : "transparent")
        border.width: root.visualFocus ? 2 : 0
        border.color: Theme.accent
    }
    contentItem: Item {
        Kirigami.Icon {
            anchors.centerIn: parent
            width: root.size * root.iconScale
            height: width
            source: root.iconName
            color: root.filled ? "white" : root.tint
            isMask: true
        }
    }
    ToolTip.visible: tip !== "" && hovered
    ToolTip.text: tip
    ToolTip.delay: 600
}
