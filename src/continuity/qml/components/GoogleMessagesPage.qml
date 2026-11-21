import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine
import org.kde.kirigami as Kirigami

// Google Messages for Web embedded as an alternative view: full RCS (iPhone chats included).
// Notifications are left to KDE Connect, which already mirrors the phone's notifications.
Rectangle {
    id: root
    color: Theme.windowBg

    WebEngineProfile {
        id: gmProfile
        storageName: "google-messages"
        offTheRecord: false
        persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies
        httpCacheType: WebEngineProfile.DiskHttpCache
        // Google serves a "browser not supported" page to user agents that name QtWebEngine
        Component.onCompleted: {
            httpUserAgent = httpUserAgent.replace(/ QtWebEngine\/[\d.]+/, "")
            httpAcceptLanguage = Qt.uiLanguage ? Qt.uiLanguage.replace("_", "-") + ",en;q=0.5" : httpAcceptLanguage
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // slim toolbar
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            Layout.leftMargin: 14
            Layout.rightMargin: 8
            spacing: 6
            Label {
                text: qsTr("Google Messages")
                font.weight: Font.DemiBold
                color: Theme.text
                Layout.fillWidth: true
            }
            BusyIndicator { running: web.loading; visible: running; Layout.preferredHeight: 22; Layout.preferredWidth: 22 }
            IconButton { iconName: "go-previous-symbolic"; tip: qsTr("Back"); enabled: web.canGoBack; onClicked: web.goBack() }
            IconButton { iconName: "view-refresh-symbolic"; tip: qsTr("Reload"); onClicked: web.reload() }
            IconButton {
                iconName: "internet-web-browser-symbolic"; tip: qsTr("Open in browser")
                onClicked: Qt.openUrlExternally(web.url)
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.separator }

        WebEngineView {
            id: web
            Layout.fillWidth: true
            Layout.fillHeight: true
            profile: gmProfile
            // the QR-code pairing page; once paired it redirects to the conversations
            url: "https://messages.google.com/web/authentication"
            backgroundColor: Theme.windowBg

            // links in messages open in the default browser, not inside the app
            onNewWindowRequested: (request) => Qt.openUrlExternally(request.requestedUrl)
            onNavigationRequested: (request) => {
                const host = request.url.toString().split("/")[2] || ""
                const google = /(^|\.)(google\.com|gstatic\.com|googleusercontent\.com|youtube\.com)$/.test(host)
                if (request.isMainFrame && request.navigationType === WebEngineNavigationRequest.LinkClickedNavigation && !google) {
                    request.reject()
                    Qt.openUrlExternally(request.url)
                }
            }
            // allow the page to read/write the clipboard; keep notifications off (KDE Connect has them)
            onPermissionRequested: (permission) => {
                if (permission.permissionType === WebEnginePermission.PermissionType.ClipboardReadWrite)
                    permission.grant()
                else
                    permission.deny()
            }
            Component.onCompleted: {
                settings.javascriptCanAccessClipboard = true
                settings.javascriptCanPaste = true
                settings.localStorageEnabled = true
                settings.playbackRequiresUserGesture = false
            }
        }
    }
}
