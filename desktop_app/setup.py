"""
YouTube Video Generator - Desktop Application
===============================================

A simple desktop wrapper for the YouTube video generation pipeline.

INSTALLATION
------------
1. Ensure Python 3.8+ is installed
2. Install dependencies:
   pip install pywebview

RUNNING
-------
Double-click or run:
   python desktop_app/launcher.py

Or create a shortcut to launcher.py

FEATURES
--------
- Native desktop window (no browser needed)
- Real-time progress in terminal
- Video gallery with open button
- Cross-platform (Windows, macOS, Linux)

BUILDING EXECUTABLE
-------------------
Install PyInstaller:
   pip install pyinstaller

Build:
   pyinstaller --onefile --windowed desktop_app/launcher.py --name YouTubeVideoGenerator

The executable will be in dist/ folder.
"""

from setuptools import setup, find_packages

setup(
    name="youtube-video-generator-desktop",
    version="1.0.0",
    description="Desktop application for AI-powered YouTube video generation",
    author="Your Name",
    packages=find_packages(),
    install_requires=[
        "pywebview>=4.0",
    ],
    entry_points={
        "console_scripts": [
            "youtube-generator=desktop_app.launcher:main",
        ],
    },
    python_requires=">=3.8",
)
