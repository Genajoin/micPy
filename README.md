# micPy

**Speech-to-Text client for OpenAI-compatible APIs**

micPy is a terminal speech-recognition client that uses an OpenAI-compatible API. It supports an interactive TUI editor and a background daemon for voice input triggered by a keyboard shortcut.

---

## 🚀 Quick Start

### System dependencies

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install portaudio19-dev python3-pyaudio xclip wl-clipboard
```

> `xclip` for X11, `wl-clipboard` for Wayland. You can install both.

**For automatic text injection on Wayland:**
```bash
sudo apt install wtype
```

> `wtype` lets you inject text directly into the active window without pressing Ctrl+V. Without it, text is copied to the clipboard.

**macOS:**
```bash
brew install portaudio
```

### Installation

```bash
git clone https://github.com/Genajoin/micPy.git
cd micPy
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## 📱 Usage

### Commands

```bash
micpy                          # TUI editor (interactive)
micpy --api-url http://localhost:5092/v1  # Specify API URL
micpy --test                   # Test mode

micpy daemon                   # Background voice-input service
micpy trigger                  # Send a trigger to the daemon

mic-stream                     # Alias for micpy
```

### TUI Editor

Interactive terminal editor with voice input:

| Key | Action |
|-----|--------|
| F1 | Show/hide help |
| F5 | Start/stop recording |
| F3 | Copy all text |
| F8 | Clear text |
| Ctrl+A | Select all |
| Ctrl+C / Ctrl+Q | Quit |

### Background daemon

For voice input bound to a hotkey:

1. Start the daemon:
   ```bash
   micpy daemon &
   micpy daemon --output-mode clipboard  # Clipboard only
   ```

**Text-output modes (`--output-mode`):**
- `auto` — wtype if installed, otherwise clipboard (default)
- `injection` — direct injection via wtype only (requires wtype)
- `clipboard` — clipboard only (Ctrl+V)

**Wayland limitations:**
- On Wayland, text is injected into the **currently active window**
- Stay in the target window during and right after recording
- xdotool/pynput do not work on Wayland

**GNOME/Wayland:** clipboard is the only working option for Russian text.

| Tool | Sway/Hyprland | GNOME/Wayland | Unicode |
|------|---------------|---------------|---------|
| wtype | ✅ | ❌ No virtual keyboard | ✅ |
| pynput | ❌ | ❌ Requires X11 | ✅ |
| ydotool | ✅ | ✅ But needs root | ❌ |

> Automatic injection on GNOME/Wayland isn't possible without root — this is a GNOME limitation.

2. Bind the trigger to a hotkey in your desktop environment:
   ```bash
   micpy trigger
   ```

 - **GNOME:** Settings → Keyboard → Custom Shortcuts
 - **KDE:** System Settings → Shortcuts

3. Press the hotkey to start recording, press again to stop and transcribe

### Running the daemon via systemd

For auto-start on login:

1. Create the service file:
   ```bash
   nano ~/.config/systemd/user/micpy-daemon.service
   ```

2. File contents:
   ```ini
   [Unit]
   Description=MicPy Voice Input Daemon
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=/path/to/micPy
   ExecStart=/path/to/micPy/.venv/bin/micpy daemon
   Restart=on-failure
   RestartSec=5
   # Pass environment for clipboard access on Wayland/X11
   PassEnvironment=WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS
   # Wait for Wayland/session initialisation before start
   ExecStartPre=/bin/sleep 2

   [Install]
   WantedBy=default.target
   ```

   Replace `/path/to/micPy` with the actual project path.

   > **Important:** `PassEnvironment` is required for clipboard access. Without it the daemon can't copy text to the clipboard on Wayland/X11.

3. Activate the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable micpy-daemon
   systemctl --user start micpy-daemon
   ```

4. Check status:
   ```bash
   systemctl --user status micpy-daemon
   ```

5. Logs:
   ```bash
   journalctl --user -u micpy-daemon -f
   ```

### Troubleshooting

**Error "Pyperclip could not find a copy/paste mechanism":**

This error occurs when systemd starts the service before the Wayland session has fully initialised.

Fix:
1. Make sure `wl-clipboard` is installed: `sudo apt install wl-clipboard`
2. Make sure the systemd unit has `ExecStartPre=/bin/sleep 2` — the delay lets Wayland finish initialising
3. Restart the service: `systemctl --user restart micpy-daemon`

**Why the delay (ExecStartPre) is needed:**
- Systemd may start user services before Wayland is initialised
- Pyperclip caches available clipboard mechanisms on first import
- If Wayland isn't ready yet, pyperclip can't find `wl-copy`/`wl-paste`

**Notification beeps are missing or play only sometimes:**

Usually the audio output falls asleep. PipeWire parks an idle sink after
5 seconds of silence, and some devices (notably HDMI outputs on NVIDIA cards)
drop the first few hundred milliseconds while waking up — the beep is only
80–120 ms, so it is swallowed whole. `pw-play` still exits with code 0, which
makes the logs look perfectly healthy.

Typical symptom: on short recordings you hear *either* the start beep *or*
the end one, but not both.

Quick check — look at the sink state after a few seconds of silence:

```bash
pw-dump | python3 -c "import json,sys; [print(o['info']['state'], o['info']['props']['node.name']) for o in json.load(sys.stdin) if (o.get('info') or {}).get('props',{}).get('media.class')=='Audio/Sink']"
```

If it says `suspended`, enable the built-in workaround:

```bash
MICPY_SOUND_KEEPALIVE=1
```

It keeps the output awake from inside the app, so no system config is touched.
See `SOUND_DEBUGGING.md` for the full diagnosis and the system-wide alternative.

---

## ⚙️ Configuration

### Environment variables

Create an `.env` file:

```bash
PARAKEET_API_URL=http://localhost:5092/v1
PARAKEET_MODEL=parakeet-tdt-0.6b-v3
```

Notification sound options (all optional, see `SOUND_DEBUGGING.md`):

| Variable | Purpose | Default |
|---|---|---|
| `MICPY_SOUND_KEEPALIVE` | Keep the audio output awake so short beeps are never swallowed | off |
| `MICPY_SOUND_WARMUP_MS` | Leading silence that "warms up" a sleeping device | 0 |
| `MICPY_SOUND_DURATION_MS` | Beep length | 80 / 120 ms |
| `MICPY_SOUND_VOLUME` | Beep amplitude, 0.0–1.0 | 0.3 |

`.env` lookup order:
- `./.env`
- `~/.env`
- `~/micpy.env`
- `~/.config/micpy/.env`

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--api-url` | http://localhost:5092/v1 | Parakeet API URL |
| `--model` | parakeet-tdt-0.6b-v3 | Transcription model |
| `--test` | - | Test mode |
| `--output-mode` | auto | Daemon output mode: auto/injection/clipboard |

---

## 🏗️ Architecture

```
micPy/
├── client/
│   ├── cli.py                # CLI entry point
│   ├── minimal_editor.py     # TUI editor
│   ├── voice_daemon.py       # Background daemon
│   ├── audio_buffer.py       # Audio capture
│   ├── parakeet_client.py    # HTTP client to the API
│   └── single_instance.py    # Single-instance lock
├── pyproject.toml
└── README.md
```

---

## 🔗 API requirements

An OpenAI-compatible STT endpoint is required:

- `POST /v1/audio/transcriptions` — audio transcription
- `GET /health` — availability check (optional)

Recommended as of early 2026: Parakeet-tdt-0.6b-v3 with CPU inference.
Recommended install via Docker Compose:

```bash
git clone https://github.com/groxaxo/parakeet-tdt-0.6b-v3-fastapi-openai
cd parakeet-tdt-0.6b-v3-fastapi-openai
docker compose up parakeet-cpu -d
```
---

## 👤 Author

Evgeny Istomin

## 📜 License

MIT License © 2025
