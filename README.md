# NEO HandNav

NEO HandNav will be a Python desktop tool that uses webcam hand gestures to control pages, slides, and videos.

> **Current status:** Project setup only. The features have not been implemented yet.

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

Clone the repository and enter the project folder.

```bash
git clone https://github.com/rmit-nct/NeoHandNav.git
cd NeoHandNav
```

Create and activate a virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python3 -m venv .venv
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

Check that the starter repository runs.

```bash
python main.py
```

Expected output:

```text
NEO HandNav project setup is ready.
```

## Technology

Python 3.11, MediaPipe, OpenCV, PyAutoGUI, and python-dotenv.

## Note

This is a temporary setup README. The team will rewrite it after finishing the project to include the completed features, usage instructions, demo, contributions, results, and known limitations.
