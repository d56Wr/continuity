import QtQuick
import QtQuick.Controls

// Small rounded text button drawn from Theme colours (so it matches light/dark on any style).
AbstractButton {
    id: root
    property bool primary: false
    implicitHeight: 28
    implicitWidth: label.implicitWidth + 24
    hoverEnabled: true
    focusPolicy: Qt.NoFocus
    background: Rectangle {
        radius: height / 2
        color: root.primary ? (root.down ? Qt.darker(Theme.accent, 1.2) : root.hovered ? Qt.lighter(Theme.accent, 1.1) : Theme.accent)
                            : (root.down ? Theme.selected : root.hovered ? Theme.hover : Theme.fieldBg)
    }
    contentItem: Text {
        id: label
        text: root.text
        color: root.primary ? "white" : Theme.text
        font.pointSize: Theme.fontSize * 0.95
        font.weight: Font.Medium
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
