# NEO HandNav

NEO HandNav is a Python desktop app that uses a webcam to control the mouse, browser navigation, scrolling, and media playback with hand gestures.

## Requirements

- Python 3.11
- A webcam
- Windows, macOS, or Linux
- The target window on the primary monitor for pointer control

## Install

```bash
git clone https://github.com/rmit-nct/NeoHandNav.git
cd NeoHandNav
python -m venv .venv
```

Activate the environment and install dependencies.

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

## Run

Start with the local browser practice page:

```bash
python main.py --practice
```

Start normally:

```bash
python main.py
```

Windows users can also run `run_handnav.cmd` after setup. Only run one HandNav process at a time so the webcam is not shared between instances.

The app starts in dry-run mode by default. Press **E** or click **Input** in the preview to enable real mouse and keyboard input. The header changes to `LIVE INPUT`.

Preview controls:

| Key | Action |
|---|---|
| E | Enable or disable real input |
| P | Pause or resume HandNav |
| M | Switch Mouse/Navigation mode |
| H | Show gesture help |
| T | Open the browser practice page |
| Q or Esc | Quit |

## Gestures

Mouse mode is the default.

| Gesture | Action |
|---|---|
| Point with index finger | Move the cursor |
| While pointing, extend the middle finger and hold briefly | Single click at the locked cursor position |
| Hold thumbs-up | Double click |
| Show thumbs-down briefly, then point again | Right click |
| Hold fist | Play/pause once |
| Open palm until `READY`, then two fingers up/down | Scroll up/down |
| Open palm until `READY`, then two fingers left/right | Browser Back/Forward |
| Open palm | Stop movement, cancel pending input, and arm navigation |

The gesture before two fingers determines the action:

- **Point → two fingers** means click.
- **Open palm → two fingers** means scroll or browser navigation.

After a click or fist action, return to Point or Open Palm before repeating it. Keep the wrist and all fingers inside the camera image; the blue rectangle only shows the pointer mapping area. Moving the physical mouse suspends gesture control, and an open palm resumes it.

## Browser notes

- Keep the pointer over the page or control you want to use.
- Browser Back/Forward uses `Alt+Left/Right` on Windows/Linux and `Command+Left/Right` on macOS.
- A disabled browser Back/Forward button means there is no history entry to open.
- For YouTube play/pause, set `PLAY_PAUSE_KEY=k` in `.env` and focus the video player once.
- `SENT` means HandNav emitted the input. It does not guarantee that the website accepted it.
- `WAITING` explains a focus or target problem. Follow the message shown in the preview.

## Useful options

```bash
python main.py --practice
python main.py --dry-run
python main.py --mode mouse
python main.py --mode navigation
python main.py --trace recordings/session.jsonl
```

Common `.env` settings:

| Setting | Purpose |
|---|---|
| `CAMERA_INDEX` | Select the webcam |
| `ACTIONS_ENABLED` | Enable real input at startup |
| `CONTROL_MODE` | Start in `mouse` or `navigation` mode |
| `NAVIGATION_TARGET` | Use `browser` history or `slides` arrow keys |
| `POINT_HOLD_MS` / `CLICK_HOLD_MS` | Point rearm and click confirmation time |
| `POINTER_BUFFER_MS` | Reduce cursor drift while changing gesture |
| `POINTER_DEADZONE_PX` | Ignore tiny pointer movements |
| `SCROLL_AMOUNT` / `SCROLL_COOLDOWN_MS` | Scroll distance and repeat speed |
| `FIST_HOLD_MS` / `PLAY_PAUSE_KEY` | Playback gesture timing and key |

Restart HandNav after editing `.env`. Keep `.env` and `.venv` local; do not commit them.

## Troubleshooting

- **Gesture is recognized but nothing happens:** enable `LIVE INPUT`, then read the status and Last input lines. A gesture label alone does not mean the action is armed.
- **Click does not trigger:** point until cursor control is active, then extend the middle finger and hold briefly. Keep the full hand visible.
- **Scroll does not trigger:** show an open palm until `READY`, place the pointer over the browser content, then hold two fingers vertically.
- **Playback says `SENT` but continues:** focus the video player and use `PLAY_PAUSE_KEY=k` for YouTube.
- **Cursor stops after using the physical mouse:** show an open palm to resume gesture control.
- **Camera does not open:** close other camera apps or change `CAMERA_INDEX`.

Run the automated checks with:

```bash
python -m unittest discover -s tests
```

Detailed engineering notes and trace instructions are available in [docs/gesture-debugging.md](docs/gesture-debugging.md).

## Technology

Python 3.11, MediaPipe, OpenCV, PyAutoGUI, and python-dotenv.
