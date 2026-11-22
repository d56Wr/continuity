import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import org.kde.kirigami as Kirigami
import "components"

ApplicationWindow {
    id: win
    width: 1120
    height: 740
    minimumWidth: 860
    minimumHeight: 540
    title: "Continuity"
    color: Theme.windowBg

    // close = hide to tray; the app keeps running for calls and notifications
    onClosing: (close) => { close.accepted = false; win.hide() }

    property int page: 0

    Shortcut { sequence: StandardKey.Find; onActivated: { win.page = 0; messages.focusSearch() } }
    Shortcut { sequence: StandardKey.New; onActivated: { win.page = 0; messages.newMessage() } }
    Shortcut { sequences: ["Ctrl+1"]; onActivated: win.page = 0 }
    Shortcut { sequences: ["Ctrl+2"]; onActivated: win.page = 1 }
    Shortcut { sequences: ["Ctrl+3"]; onActivated: win.page = 2 }
    Shortcut { sequences: ["Ctrl+4"]; onActivated: win.page = 3 }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            Layout.fillHeight: true
            Layout.preferredWidth: 232
            current: win.page
            onSelected: (i) => win.page = i
        }

        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: Theme.separator }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: win.page

            MessagesPage { id: messages; onCallNumber: (n) => calls.dialNumber(n) }
            CallsPage { id: calls; onMessageNumber: (n) => { win.page = 0; messages.composeTo(n) } }
            NotificationsPage {}
            PhonePage {}
        }
    }

    NotConnectedOverlay {
        anchors.fill: parent
        visible: !phone.connected
    }

    Toast { id: toast; z: 60 }
    Connections { target: phone; function onToast(text) { toast.show(text) } }
    Connections {
        target: phone
        function onOpenThreadRequested(tid) { win.page = 0; messages.openConversation(tid) }
    }
}
