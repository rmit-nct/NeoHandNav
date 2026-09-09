# NEO HandNav

NEO HandNav will be a Python desktop tool that uses webcam hand gestures to control pages, slides, and videos.

> **Current status:** Camera capture, hand tracking, gesture classification, safe action mapping, and the main integration loop are available. Actions start in dry-run mode.

## Project structure

```text
NeoHandNav/
|-- backend/
|   |-- __init__.py
|   |-- hand_tracker.py
|   |-- gesture_classifier.py
|   |-- gesture_controller.py
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

Run the current camera and hand-landmark test.

```bash
python main.py
```

The program opens the webcam, draws hand landmarks, and displays the detected gesture and action status. Press `q` in the camera window to stop it.

## Current gesture controls

| Gesture | Result |
|---|---|
| Hold an open palm until `READY` | Arm a new interaction; stop the previous one |
| Hold index + middle fingers left/right, ring + pinky folded | Previous/next slide (Left/Right arrow) |
| Hold index + middle fingers up/down, ring + pinky folded | Repeat scroll up/down |
| Touch thumb + index, keep other fingers folded, then spread/close | Zoom in/out during that pinch session |
| Hold a fist briefly | Send Space once (play/pause when the player has focus) |
| Point with index only | Recognition only; ends an active scroll session |

These are the **static controls on the current branch**. Earlier Word blueprints describe swipes and moving-palm scrolling; those are not the controls implemented here. Page direction follows the mirrored camera preview. An upper diagonal also selects a page direction; keep the two fingers nearly vertical for scrolling.

Show an open palm before each new interaction. Hold a directional pose still for about 220 ms to start it; after recognition, small hand movements do not restart scrolling. Fist requires at least 150 ms plus three frames. The displayed score is a geometry heuristic, not a measured recognition probability.

No hand, multiple detected hands, invalid landmarks, or a frame gap over 500 ms resets the controls. Brief uncertain frames send no commands; an established scroll may resume within 350 ms. A longer interruption or a different recognized pose ends the session and requires a fresh open palm.

The default `ACTIONS_ENABLED=false` in `.env` is safe dry-run mode: gestures are recognized and displayed without controlling the computer. Change it to `true` only when testing OS control, then focus the browser, slides, or video you want to control. PyAutoGUI's upper-left-corner fail-safe remains enabled.

An OS execution error, including the fail-safe, switches actions to dry run until an explicit re-enable or restart. Keyboard shortcuts act on the focused app: **Space can scroll an ordinary browser page**, and arrow keys change slides only in an app that supports those shortcuts. Click the video player before testing fist. Watch the last command in the overlay: `play or pause ('space',)` is different from `scroll down (-1,)`.

New defaults use `SCROLL_AMOUNT=1` and `SCROLL_COOLDOWN_MS=60` for smaller, more frequent wheel steps. If an older `.env` explicitly sets `SCROLL_COOLDOWN_MS=220`, update those two settings to try the new pacing. Keep your other local settings.

Run the logic tests without opening the webcam:

```bash
python -m unittest discover -s tests -v
```

Record a failing webcam session as local landmark data, then replay it without the camera or OS input:

```bash
python main.py --trace recordings/meeting-test.jsonl
python -m scripts.replay_gestures recordings/meeting-test.jsonl
```

Use a new filename for each recording. Traces contain hand coordinates, timestamps, configuration, recognized labels, and commands; they do not contain video or screenshots. `recordings/` is ignored by Git. Replay reports actions and differences from the recorded result. See [the debugging and meeting test guide](docs/gesture-debugging.md) for findings and live checks.

## Technology

Python 3.11, MediaPipe, OpenCV, PyAutoGUI, and python-dotenv.

## Note

The `.venv` and `.env` files are local and must not be pushed. Every teammate creates their own `.venv` after cloning and installs the shared `requirements.txt`.

This is a temporary setup README. The team will rewrite it after finishing the project to include the completed features, usage instructions, demo, contributions, results, and known limitations.
