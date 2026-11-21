<p align="center"><img src="src/continuity/data/continuity.svg" width="112" alt=""></p>

<h1 align="center">Continuity</h1>

<p align="center"><b>Your Android phone on the Linux desktop</b> — messages, calls and notifications in one window,<br>
in the spirit of macOS Continuity / iPhone integration.</p>

---

Continuity is a small Qt/QML desktop app that brings together what Linux can already do with an
Android phone, behind one clean, macOS-style interface:

| | |
|---|---|
| 💬 **Messages** | Full SMS/MMS conversation history, replies, new messages, contact names and photos, image thumbnails |
| 📞 **Calls** | Incoming-call banner with **Answer / Decline**, in-call HUD (timer, mute, hang up), dial pad and contacts. Call audio runs through the PC's microphone and speakers/headphones |
| 🔔 **Notifications** | Everything that shows up on the phone, with **dismiss on the phone**, *Clear all* and quick replies |
| 📱 **Phone** | Battery, signal, *Find my phone*, send files (drag & drop, "AirDrop"), browse phone storage, send clipboard |
| 🧩 **Desktop** | Tray icon, runs in the background, starts at login, `continuity --answer` / `--hangup` for global shortcuts or a Stream Deck key, English and Czech UI |

## How it works

Continuity does not reimplement any phone protocol. It is a front end over two mature pieces:

- **[KDE Connect](https://kdeconnect.kde.org/)** (over Wi-Fi) — messages, contacts, notifications,
  battery, file transfer. Continuity talks to the running `kdeconnectd` over D-Bus.
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
- RCS chats are not visible to KDE Connect, only SMS/MMS.
- Call history and voicemail are not available.

## License

GPL-3.0-or-later. Not affiliated with Apple, Google or KDE.
