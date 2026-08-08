# NEO HandNav

NEO HandNav will be a Python desktop tool that uses webcam hand gestures to control pages, slides, and videos.

> **Current status:** Camera capture and MediaPipe hand-landmark tracking are available. Gesture classification and action mapping are still team tasks.

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

The program should open the webcam, draw the detected hand landmarks, and print fingertip coordinates. Press `q` in the camera window to stop it.

## Technology

Python 3.11, MediaPipe, OpenCV, PyAutoGUI, and python-dotenv.

## Note

The `.venv` and `.env` files are local and must not be pushed. Every teammate creates their own `.venv` after cloning and installs the shared `requirements.txt`.

This is a temporary setup README. The team will rewrite it after finishing the project to include the completed features, usage instructions, demo, contributions, results, and known limitations.
