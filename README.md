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
|   `-- action_mapper.py
|-- ui/
|   |-- __init__.py
|   `-- feedback_overlay.py
|-- tests/
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
| Swipe left or right | Previous or next page/slide |
| Move an open palm up or down | Scroll up or down |
| Move thumb and index apart/together | Zoom in or out |
| Fist | Play or pause |
| Point | Display recognition only |

The default `ACTIONS_ENABLED=false` in `.env` is safe dry-run mode: gestures are recognized and displayed without controlling the computer. Change it to `true` only when testing OS control, then focus the browser, slides, or video you want to control. PyAutoGUI's upper-left-corner fail-safe remains enabled.

Run the logic tests without opening the webcam:

```bash
python -m unittest discover -s tests -v
```

## Technology

Python 3.11, MediaPipe, OpenCV, PyAutoGUI, and python-dotenv.

## Note

The `.venv` and `.env` files are local and must not be pushed. Every teammate creates their own `.venv` after cloning and installs the shared `requirements.txt`.

This is a temporary setup README. The team will rewrite it after finishing the project to include the completed features, usage instructions, demo, contributions, results, and known limitations.
