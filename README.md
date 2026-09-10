# NEO HandNav

NEO HandNav is a Python desktop app for pointing, clicking, scrolling, and keyboard navigation using a webcam.

> **Current status:** Mouse and Navigation modes are implemented. Start with the built-in browser practice page. The default configuration previews gestures in dry run; enable real input with the **Input** button or **E** in the preview.

## Project structure

```text
NeoHandNav/
|-- backend/
|   |-- __init__.py
|   |-- hand_tracker.py
|   |-- gesture_classifier.py
|   |-- gesture_controller.py
|   |-- pointer_controller.py
|   `-- action_mapper.py
|-- ui/
|   |-- __init__.py
|   `-- feedback_overlay.py
|-- tests/
|-- scripts/
|-- docs/
|-- .env.example
|-- .gitignore
|-- main.py
|-- run_handnav.cmd
|-- README.md
`-- requirements.txt
```

`backend` contains the desktop application's processing logic. It is not a web server.

## Setup

Install **Python 3.11.x** first. Use this version on every teammate's computer so everyone matches the environment tested for this repository.

Clone the repository and enter the project folder.

```bash
git clone https://github.com/rmit-nct/NeoHandNav.git
cd NeoHandNav
```

Create and activate a virtual environment.

Windows PowerShell:

```powershell
# Install Python once; skip this command if Python 3.11 is already installed.
winget install --exact --id Python.Python.3.11 --scope user

& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Install the dependencies.

```bash
python -m pip install -r requirements.txt
```

Create the local environment file.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS or Linux:

```bash
cp .env.example .env
```

Run with a local browser practice page:

```bash
python main.py --practice
```

On Windows you can also double-click `run_handnav.cmd` after setup, or run `run_handnav.cmd --practice`. Stop an older running copy before starting the updated app. Only one process should own the webcam.

The camera panel has buttons for **Input**, **Pause**, **Mode**, **Help**, **Test**, and **Quit**. The equivalent keys are E, P, M, H, T, and Q/Esc while the panel has focus. The full camera image is visible below the status panel. Click the Input button to enable OS control; the header changes from **DRY RUN** to **LIVE INPUT**. These buttons change the running session, not your `.env` file.

## Mouse mode (default)

Point your **index finger** with the other fingers folded. Move the visible fingertip within the outlined camera area; its position maps to the primary monitor. You can move your whole hand to reach a target. Hold the point briefly (about 180 ms after recognition) to start moving. No open-palm gate is needed for mouse movement.

| Gesture | Result |
|---|---|
| Index-only point | Move the mouse with adaptive smoothing |
| Point at a target, then extend the middle finger too; hold briefly | One single left click at the locked target; about 180 ms after the two-finger pose is recognized |
| Point at a target, then hold thumbs-up until the progress bar fills (about 0.9 seconds after recognition) | One double left click; holding longer does not repeat |
| Point at a target, show thumbs-down briefly, then point again | Right click |
| Open palm until READY, then two fingers vertically up/down, ring and pinky folded | Repeated wheel scrolling at the current pointer location |
| Open palm until READY, then two fingers left/right | Browser Back/Forward, like the toolbar buttons |
| Open palm until READY, then pinch and spread/close | Zoom in/out |
| Hold a fist until the bar fills | One playback toggle; holding longer does not repeat |
| Open palm | Stop movement, cancel pending clicks, prepare navigation |

**Point then two fingers means click, regardless of finger direction. Palm then two fingers means navigation.** Once active pointing has selected clicking, holding or rotating the two-finger pose cannot scroll or send arrows. Fold the middle finger to return to pointing before another click. A middle-finger opening signal freezes the cursor before the full two-finger pose passes recognition/debounce, reducing drift during the transition.

Thumbs-up remains an optional double-click gesture: hold until the bar fills. A shorter thumbs-up followed by Point still provides an alternative single click. Thumbs-down provides right click. These thumb gestures use the current cursor position and no longer impose a 400 ms deadline after pointing. A double click never receives an extra speculative single click. Open palm, fist, hand loss, multiple hands, a long uncertainty gap, pause, changing mode, or changing input enablement cancels pending clicks. A held fist subsequently sends playback only after its own dwell.

Use **single click** for links, buttons, and selecting an item. Use **double click** when the target app expects it, such as opening a file in a default desktop file manager. HandNav does not guess based on what is under the cursor. The target application controls the meaning of the received clicks.

Moving your physical mouse more than 30 pixels away from the last gesture position suspends gesture control, so you can take over. Show an open palm to resume. Mouse gestures currently target the **primary monitor**. Move the target window there. Drag-and-drop and multi-monitor pointer mapping are not implemented.

### Reducing pointer shake during clicking

Mouse motion now passes through a **100 ms buffer** before it reaches the visible cursor. When the middle finger starts opening, a click pose is recognized, or recognition becomes uncertain, pending motion is discarded. This prevents brief transition shake from moving the target and keeps the click at the position you see. A **2-pixel deadzone** also suppresses tiny filtered movements while hovering. Returning to pointing clears the old motion/velocity state and starts from the visible cursor.

This adds about 100 ms to movement latency; it cannot eliminate movement that lasts longer than the buffer or starts well before the pose transition. In `.env`, `POINTER_BUFFER_MS=100` controls the delay (0–250 ms) and `POINTER_DEADZONE_PX=2` controls the small movement threshold (0–10 pixels). Setting either to zero disables that feature. Restart after changing settings. The pointing and click gestures themselves are unchanged.

## Navigation mode

Click **Mode** / press **M**, or start with `python main.py --mode navigation` for keyboard/scroll controls without cursor movement. These controls are also available in Mouse mode using the activation conditions above:

| Gesture | Result |
|---|---|
| Hold an open palm until `READY` | Arm a new interaction; stop the previous one |
| Hold index + middle fingers left/right, ring + pinky folded | Browser Back/Forward (default); slide arrows with `NAVIGATION_TARGET=slides` |
| Hold index + middle fingers up/down, ring + pinky folded | Repeat scroll up/down |
| Touch thumb + index, keep other fingers folded, then spread/close | Zoom in/out during that pinch session |
| Hold a fist briefly | Send the configured play/pause key once |
| Point with index only | Recognition only; switch to Mouse mode to move the cursor |
| Thumbs-up/down | Recognition only; no Space key |

These are static controls. Earlier Word blueprints describe swipes and moving-palm scrolling; those are not the controls implemented here. Page direction follows the mirrored camera preview. An upper diagonal also selects a page direction; keep the two fingers nearly vertical for scrolling.

In Navigation mode, show an open palm before each new interaction and wait for **READY**. Hold a directional pose still for about 220 ms to start it; after recognition, small hand movements do not restart scrolling. Fist requires at least 150 ms plus three frames. Gesture classification uses geometry heuristics; it is not a calibrated probability model.

No hand, multiple detected hands, invalid landmarks, or a frame gap over 500 ms resets the controls. Brief uncertain frames send no commands; a navigation scroll may resume within 350 ms. A longer interruption or a different recognized pose ends the navigation session and requires a fresh open palm. Mouse clicking allows up to 800 ms of uncertain classifications while forming/releasing a pose. Uncertain time does not advance click or fist hold timers. Completed click/playback latches survive tracking interruptions, so a held pose cannot repeat merely because recognition briefly drops out.

## Input, focus, and tuning

The default `ACTIONS_ENABLED=false` in `.env` previews gestures without controlling the computer. Enable input with **E** or the Input button when ready. `python main.py --dry-run` overrides the saved startup setting. Keep PyAutoGUI's corner fail-safe enabled.

An OS execution error, including the fail-safe, switches actions to dry run until you explicitly re-enable or restart. The error remains visible. On Windows, Fist now sends the **play/pause media key** in either mode. Start the intended video first so it has an active media session. Windows/browser media routing decides the recipient; with multiple media sessions it may select a different player. YouTube documents this key for playback in its [keyboard shortcut guide](https://support.google.com/youtube/answer/7631406?hl=en). It toggles play/pause; it does not inspect whether a video is currently paused.

For a player without media-key support, set `PLAY_PAUSE_KEY=k` (YouTube) or `PLAY_PAUSE_KEY=space`, then focus that player before testing. Space is the default on other platforms and can scroll a normal browser page. `SENT` means the input call completed, not that the app acknowledged it. You can always use the two-finger single click on the player's actual pause button.

**Browser Back/Forward:** the default `NAVIGATION_TARGET=browser` sends Alt+Left / Alt+Right on Windows/Linux, or Command+Left / Command+Right on macOS, following [Chrome's shortcut documentation](https://support.google.com/chrome/answer/157179?hl=en). Keep the browser focused and show palm before each history gesture. A grey toolbar button means that direction has no history entry; the gesture cannot create one. These controls navigate tab history, not YouTube's previous/next Short buttons. Click those in-page buttons with Point → two fingers. For presentations, set `NAVIGATION_TARGET=slides` to retain plain arrow keys. This setting applies in both Mouse and Navigation modes.

New defaults use `SCROLL_AMOUNT=1` and `SCROLL_COOLDOWN_MS=60` for smaller, more frequent wheel steps. If an older `.env` explicitly sets `SCROLL_COOLDOWN_MS=220`, update those two settings to try the new pacing. Keep your other local settings.

`CONTROL_MODE=mouse` is the startup default. `POINTER_MARGIN=0.15` maps the central 70% of the camera to the screen. Increase the margin if reaching screen edges is tiring. Lower `POINTER_MIN_CUTOFF` for more smoothing; increase `POINTER_SPEED_COEFFICIENT` for faster movement response. `DOUBLE_CLICK_HOLD_MS=900` adjusts the optional thumbs-up double click. `FIST_HOLD_MS=600` adjusts Mouse-mode playback dwell after recognition. Settings are validated at startup.

## Verify browser input

Run `python main.py --practice`, or click **Test** in the preview. A local page opens with single-, double-, and right-click targets, a scroll box, a keyboard playback simulation, and an event log. It has no external dependencies or camera access. First verify with a physical mouse, then use gestures. If counters change, input reached the browser. To scroll, point inside the box, show palm until READY, then two fingers down. The keyboard simulation is not a real media player: test system media routing separately against an active video.

Keep the browser and preview side by side. If you use the physical mouse to reposition windows, show an open palm before resuming gesture control. Click the browser's actual controls in Mouse mode; Navigation shortcuts are app-dependent.

Run the logic tests without opening the webcam:

```bash
python -m unittest discover -s tests -v
```

Record a failing webcam session as local landmark data, then replay it without the camera or OS input:

```bash
python main.py --trace recordings/meeting-test.jsonl
python -m scripts.replay_gestures recordings/meeting-test.jsonl
```

Use a new filename for each recording. Traces contain hand coordinates, timestamps, configuration, cursor coordinates, recognized labels, mode changes, and commands; they do not contain video or screenshots. `recordings/` is ignored by Git. Replay supports the old Navigation trace format and the new Mouse/Navigation format; it always disables OS output. See [the debugging and meeting test guide](docs/gesture-debugging.md) for findings and live checks.

Optional browser QA: install Playwright in your development environment and run `node scripts/check_browser_input.cjs` with Chrome installed. The checker first verifies the practice page, then passes synthetic hand sequences through the production classifier/controller and delivers their resulting commands into an isolated headless browser. It checks one two-finger click (no scroll/arrows), explicit double/right clicks, palm-gated scrolling, and one playback-key event. Screenshots are saved under `tmp/`. It does not test live webcam recognition, PyAutoGUI delivery, or Windows media-session routing.

On Windows, `node scripts/check_browser_input.cjs --desktop-history` additionally opens an isolated visible Chrome window and tests **real PyAutoGUI Back/Forward delivery**. The helper sends only those two shortcuts, only while the uniquely titled test window is foreground; otherwise it aborts without input. This check passed Back twice and Forward twice across three local history entries. The practice page also has a link to a second page for manual history testing. Page-level Playwright keyboard events alone do not exercise Chrome's toolbar shortcuts.

Click recognition after pointing uses its own pose rule, with perspective and mild-bend tolerance; it does not require a directional scroll pose. The pointer retains its time-based one-click confirmation and frozen target. Brief uncertain frames pause confirmation, but sparse detections cannot accumulate indefinitely: 180 ms of recognized holding must fit within a 600 ms confirmation window. Open hands, hooks, hand loss, and invalid tracking still cancel or reject clicks. If the panel reports the hand is outside the camera, bring the wrist and fingers into the full camera image; the outlined pointer area is only the cursor-mapping region, not the tracking boundary.

## Technology

Python 3.11, MediaPipe, OpenCV, PyAutoGUI, and python-dotenv.

## Note

The `.venv` and `.env` files are local and must not be pushed. Every teammate creates their own `.venv` after cloning and installs the shared `requirements.txt`.

Hand recognition still needs live testing with different users, lighting, distances, and the final demo camera. Automated geometry and browser tests do not prove universal recognition accuracy. Final submission materials (team contributions, demo recording, and report links) are maintained by the team.
