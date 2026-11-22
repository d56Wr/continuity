import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// "Message sound: [Ocean · New Message ▾] ▶" — pick a tone (or none / a custom file) and preview it.
RowLayout {
    id: root
    property string label
    property string kind            // "message" | "ring"
    property var options: []        // [{id, label}]
    property string current
    signal picked(string id)
    Layout.leftMargin: 6
    spacing: 8

    Label { text: root.label; color: Theme.text; Layout.fillWidth: true }
    ComboBox {
        id: box
        Layout.preferredWidth: 240
        model: root.options.map(o => o.label).concat([qsTr("Custom file…")])
        currentIndex: Math.max(0, root.options.findIndex(o => o.id === root.current))
        onActivated: (i) => {
            if (i === root.options.length) {   // "Custom file…"
                currentIndex = Math.max(0, root.options.findIndex(o => o.id === root.current))
                fileDialog.open()
                return
            }
            root.picked(root.options[i].id)
            phone.previewSound(root.options[i].id)
        }
    }
    IconButton {
        iconName: "media-playback-start-symbolic"
        tint: Theme.accent
        enabled: root.current !== ""
        tip: qsTr("Play")
        onClicked: phone.previewSound(root.current)
    }
    FileDialog {
        id: fileDialog
        title: qsTr("Choose a sound")
        nameFilters: [qsTr("Sounds (*.oga *.ogg *.wav *.flac)")]
        onAccepted: phone.setCustomSound(root.kind, selectedFile)
    }
}
