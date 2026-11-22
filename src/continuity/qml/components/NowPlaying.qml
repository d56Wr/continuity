import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// What's playing on the phone (KDE Connect "multimedia control"): art, title, seek, transport.
Rectangle {
    id: root
    implicitHeight: row.implicitHeight + 28
    radius: 14
    color: Theme.cardBg
    border.color: Theme.separator

    // position is only reported on changes; interpolate while playing
    property real pos: phone.mediaPosition
    property double posAt: Date.now()
    Connections {
        target: phone
        function onMediaChanged() { root.pos = phone.mediaPosition; root.posAt = Date.now() }
    }
    Timer {
        interval: 500; repeat: true
        running: phone.mediaPlaying && root.visible && !seek.pressed
        onTriggered: seek.value = Math.min(phone.mediaLength, root.pos + (Date.now() - root.posAt))
    }
    function fmt(ms) {
        const s = Math.max(0, Math.floor(ms / 1000))
        const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60
        return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(sec).padStart(2, "0")
    }

    RowLayout {
        id: row
        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 14 }
        spacing: 14

        Rectangle {
            Layout.preferredWidth: 72; Layout.preferredHeight: 72
            radius: 10
            color: Theme.fieldBg
            clip: true
            Image {
                id: art
                anchors.fill: parent
                source: phone.mediaArt
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
            }
            Kirigami.Icon {
                anchors.centerIn: parent
                visible: art.status !== Image.Ready
                width: 32; height: 32
                source: "media-playback-start-symbolic"; color: Theme.secondary; isMask: true
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            RowLayout {
                Label {
                    Layout.fillWidth: true
                    text: phone.mediaTitle
                    font.weight: Font.DemiBold
                    color: Theme.text
                    elide: Text.ElideRight
                }
                ComboBox {   // more than one player app on the phone (e.g. Spotify + an audiobook app)
                    visible: phone.mediaPlayers.length > 1
                    model: phone.mediaPlayers
                    currentIndex: phone.mediaPlayers.indexOf(phone.mediaPlayer)
                    onActivated: (i) => phone.mediaSelectPlayer(phone.mediaPlayers[i])
                    implicitHeight: 26
                    font.pointSize: Theme.fontSize * 0.85
                }
            }
            Label {
                Layout.fillWidth: true
                text: [phone.mediaArtist, phone.mediaAlbum].filter(s => s).join(" — ")
                color: Theme.secondary
                elide: Text.ElideRight
            }
            RowLayout {
                spacing: 8
                visible: phone.mediaLength > 0
                Label { text: root.fmt(seek.value); color: Theme.secondary; font.features: { "tnum": 1 }; font.pointSize: Theme.fontSize * 0.85 }
                Slider {
                    id: seek
                    Layout.fillWidth: true
                    from: 0; to: Math.max(1, phone.mediaLength)
                    value: root.pos
                    enabled: phone.mediaCanSeek
                    onPressedChanged: if (!pressed) { phone.mediaSeekTo(value); root.pos = value; root.posAt = Date.now() }
                }
                Label { text: "-" + root.fmt(phone.mediaLength - seek.value); color: Theme.secondary; font.features: { "tnum": 1 }; font.pointSize: Theme.fontSize * 0.85 }
            }
        }

        RowLayout {
            spacing: 4
            IconButton { size: 36; iconName: "media-skip-backward-symbolic"; tint: Theme.text; tip: qsTr("Previous"); onClicked: phone.mediaAction("Previous") }
            IconButton {
                size: 44; filled: true; fill: Theme.accent
                iconName: phone.mediaPlaying ? "media-playback-pause-symbolic" : "media-playback-start-symbolic"
                tip: phone.mediaPlaying ? qsTr("Pause") : qsTr("Play")
                onClicked: phone.mediaAction("PlayPause")
            }
            IconButton { size: 36; iconName: "media-skip-forward-symbolic"; tint: Theme.text; tip: qsTr("Next"); onClicked: phone.mediaAction("Next") }
        }
    }
}
