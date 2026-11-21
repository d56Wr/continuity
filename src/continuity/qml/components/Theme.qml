pragma Singleton
import QtQuick
import org.kde.kirigami as Kirigami

// Colours follow the system palette (light/dark); accents follow macOS.
QtObject {
    readonly property bool dark: Kirigami.ColorUtils.brightnessForColor(Kirigami.Theme.backgroundColor) === Kirigami.ColorUtils.Dark

    readonly property color accent: dark ? "#0a84ff" : "#007aff"
    readonly property color green: dark ? "#30d158" : "#34c759"
    readonly property color red: dark ? "#ff453a" : "#ff3b30"
    readonly property color orange: dark ? "#ff9f0a" : "#ff9500"

    readonly property color windowBg: dark ? "#1e1e1e" : "#ffffff"
    readonly property color sidebarBg: dark ? "#262626" : "#f2f2f5"
    readonly property color panelBg: dark ? "#232323" : "#fafafa"
    readonly property color cardBg: dark ? "#2c2c2e" : "#ffffff"
    readonly property color hover: dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0, 0, 0, 0.05)
    readonly property color selected: dark ? Qt.rgba(1, 1, 1, 0.11) : Qt.rgba(0, 0, 0, 0.08)
    readonly property color separator: dark ? Qt.rgba(1, 1, 1, 0.09) : Qt.rgba(0, 0, 0, 0.09)
    readonly property color text: dark ? "#f5f5f7" : "#1d1d1f"
    readonly property color secondary: dark ? "#98989d" : "#6e6e73"
    readonly property color tertiary: dark ? "#636366" : "#aeaeb2"
    readonly property color fieldBg: dark ? Qt.rgba(1, 1, 1, 0.07) : Qt.rgba(0, 0, 0, 0.05)
    readonly property color bubbleIn: dark ? "#3a3a3c" : "#e9e9eb"
    readonly property color bubbleOut: accent
    readonly property color shadow: Qt.rgba(0, 0, 0, dark ? 0.5 : 0.18)

    readonly property int radius: 10
    readonly property real fontSize: Kirigami.Theme.defaultFont.pointSize
}
