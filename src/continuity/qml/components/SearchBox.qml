import QtQuick
import QtQuick.Controls
import org.kde.kirigami as Kirigami

TextField {
    id: root
    leftPadding: 30
    rightPadding: text ? 28 : 10
    implicitHeight: 30
    color: Theme.text
    placeholderTextColor: Theme.secondary
    background: Rectangle {
        radius: 8
        color: Theme.fieldBg
        border.width: root.activeFocus ? 2 : 0
        border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.6)
    }
    // the desktop style paints its placeholder in the background we replaced, so draw our own
    property string hint: qsTr("Search")
    Label {
        anchors.left: parent.left
        anchors.leftMargin: root.leftPadding
        anchors.verticalCenter: parent.verticalCenter
        visible: root.text === "" && root.preeditText === ""
        text: root.hint
        color: Theme.secondary
    }
    Kirigami.Icon {
        anchors.left: parent.left
        anchors.leftMargin: 9
        anchors.verticalCenter: parent.verticalCenter
        width: 15; height: 15
        source: "search-symbolic"
        color: Theme.secondary
        isMask: true
    }
    IconButton {
        anchors.right: parent.right
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        visible: root.text !== ""
        size: 22
        iconName: "edit-clear-symbolic"
        onClicked: root.clear()
    }
    Keys.onEscapePressed: clear()
}
