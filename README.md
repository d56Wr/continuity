<p align="center"><img src="src/continuity/data/continuity.svg" width="112" alt=""></p>

<h1 align="center">Continuity</h1>

<p align="center"><b>Your Android phone on the Linux desktop</b> — messages, calls and notifications in one window,<br>
in the spirit of macOS Continuity / iPhone integration.</p>

---

Continuity is a small Qt/QML desktop app that brings together what Linux can already do with an
Android phone, behind one clean, macOS-style interface:

| | |
|---|---|
| 💬 **Messages** | **SMS and RCS** (iPhone chats included) via Google Messages: history, replies, new messages, photos and files, reactions, Sent / Delivered / Read, green SMS vs blue RCS bubbles, local *mark as unread*. Falls back to SMS/MMS from KDE Connect when Google Messages is not paired |
| 📞 **Calls** | Incoming-call banner with **Answer / Decline**, in-call HUD (timer, mute, hang up), dial pad and contacts. Call audio runs through the PC's microphone and speakers/headphones |
| 🔔 **Notifications** | Everything that shows up on the phone, with **dismiss on the phone**, *Clear all* and quick replies |
| 📱 **Phone** | Battery, signal, *Find my phone*, send files (drag & drop, "AirDrop"), browse phone storage, send clipboard |
| 🧩 **Desktop** | Tray icon, runs in the background, starts at login, `continuity --answer` / `--hangup` for global shortcuts or a Stream Deck key, English and Czech UI |

## How it works

Continuity is a front end over three pieces:

- **[KDE Connect](https://kdeconnect.kde.org/)** (over Wi-Fi) — messages, contacts, notifications,
  battery, file transfer. Continuity talks to the running `kdeconnectd` over D-Bus.
- **Google Messages for Web** protocol (SMS + RCS) through a small Go helper built on
  [libgm](https://github.com/mautrix/gmessages) from mautrix-gmessages (`helper/gmessages`,
  AGPL-3.0). Pairing uses your Google account: Continuity opens your Chromium-based browser
  with a separate throw-away profile, you sign in, then tap the matching emoji on the phone.
  This is an **unofficial** client; Google may change the protocol at any time.
- **Bluetooth Hands-Free (HFP)** via **PipeWire** — the PC acts like a car kit for the phone.
  PipeWire ≥ 1.2 exposes calls on D-Bus (`org.pipewire.Telephony`); Continuity answers, declines
  and dials through it and routes the call audio with `pw-loopback`.

```
 ┌─────────────┐   Wi-Fi (KDE Connect)   ┌────────────┐  D-Bus  ┌─────────────┐
 │   Android   │ ──────────────────────▶ │ kdeconnectd│ ──────▶ │             │
 │    phone    │                         └────────────┘         │ Continuity  │
 │             │   Bluetooth HFP         ┌────────────┐  D-Bus  │  (Qt/QML)   │
 │             │ ──────────────────────▶ │  PipeWire  │ ──────▶ │             │
 └─────────────┘                         └────────────┘         └─────────────┘
```

## Requirements

- Linux with a session D-Bus and a system tray (tested on KDE Plasma 6)
- Python ≥ 3.11, **PySide6** ≥ 6.6, PyGObject, Kirigami (QML module)
- **KDE Connect** on the computer and the **KDE Connect** app on the phone (Play Store / F-Droid)
- For RCS: Go ≥ 1.22 to build the helper, and Microsoft Edge / Chrome / Chromium for the one-time sign-in
- For calls: Bluetooth adapter, **PipeWire ≥ 1.2** with WirePlumber, `pw-loopback`, `pactl`

Arch / CachyOS:

```sh
sudo pacman -S pyside6 python-gobject kirigami kdeconnect pipewire-pulse
```

## Install (from source)

```sh
git clone https://github.com/<you>/continuity.git
cd continuity
./scripts/install-dev.sh     # puts a `continuity` launcher in ~/.local/bin and a menu entry
continuity
```

## Phone setup

1. Install **KDE Connect** on the phone, join the same network and pair it with the computer.
2. In the app grant SMS, phone, contacts and notification access, and enable the
   **Contacts synchronizer** plugin (for names in Messages).
3. For calls, pair the phone over **Bluetooth** with the computer and enable **Calls** for it
   (leave *Media audio* off unless you want the phone's music on the PC).

## Command line

```
continuity               open the window (or bring the running one to front)
continuity --background  start hidden in the tray
continuity --answer      answer the ringing call
continuity --hangup      decline / hang up
continuity --toggle-call answer if ringing, otherwise hang up
```

By default call audio goes to the default speaker and microphone. To send it elsewhere (for
example into a mixer channel) set `callSpeaker` / `callMicrophone` in
`~/.config/continuity/settings.json` to a PipeWire node name.

## Translations

Strings live in `po/*.ts` (Qt Linguist). Add a language with `scripts/update-translations.sh`
(edit the language list), translate the `.ts` file, then `scripts/build-translations.sh`.

## Limitations

- Calls need Bluetooth HFP; KDE Connect alone can only show and silence them.
- RCS needs Google Messages as the phone's SMS app and the (unofficial) Google Messages pairing.
- "Mark as unread" is local to Continuity: the Google Messages protocol has no such action.
- Call history and voicemail are not available.

## License

GPL-3.0-or-later. Not affiliated with Apple, Google or KDE.
