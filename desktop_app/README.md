# YouTube Video Generator - Desktop App

Simple desktop application wrapper for the YouTube video generation pipeline.

## Quick Start

### Prerequisites
- Python 3.8 or higher
- The YouTube pipeline already set up (`../requirements.txt` installed)

### Install

```bash
# Navigate to desktop_app folder
cd desktop_app

# Install the desktop app
pip install pywebview

# Or install with setup.py
pip install -e .
```

### Run

```bash
# Method 1: Direct run
python launcher.py

# Method 2: After pip install
youtube-generator
```

### Create Desktop Shortcut

**Linux:**
```bash
# Create .desktop file
cat > ~/.local/share/applications/youtube-generator.desktop << 'EOF'
[Desktop Entry]
Name=YouTube Video Generator
Exec=python3 /path/to/desktop_app/launcher.py
Icon=/path/to/icon.png
Type=Application
Categories=AudioVideo;
EOF
```

**Windows:**
Create a shortcut to `launcher.py` and set:
- Target: `pythonw.exe launcher.py`
- Start in: `desktop_app` folder

**macOS:**
Use Automator to create an application that runs the script.

## Building Standalone Executable

```bash
# Install PyInstaller
pip install pyinstaller

# Build one-file executable
pyinstaller --onefile --windowed launcher.py --name YouTubeVideoGenerator

# The app will be in: dist/YouTubeVideoGenerator
```

## Features

- **Native Window**: Runs in its own window (not browser)
- **Real-time Output**: See generation progress live
- **Auto-detect**: Finds free port automatically
- **Video Gallery**: Browse and open generated videos
- **Cross-platform**: Works on Windows, macOS, Linux

## How It Works

1. Starts a local HTTP API server (Python backend)
2. Launches pywebview window with the UI
3. UI communicates with backend via HTTP/SSE
4. Backend runs the pipeline.py script
5. Progress streamed back to UI in real-time

## Troubleshooting

**Window doesn't open:**
- Check if pywebview is installed: `pip install pywebview`
- On Linux, may need: `sudo apt install python3-gi gir1.2-webkit2-4.0`

**Pipeline not found:**
- Ensure you're in the project root directory
- Check that `pipeline.py` exists

**Port in use:**
- App auto-finds free port, should work automatically

## File Structure

```
desktop_app/
├── launcher.py      # Main entry point
├── setup.py         # Package setup
├── ui/              # Generated UI files
│   └── index.html
└── README.md        # This file
```

## License

Same as the main project (MIT)
