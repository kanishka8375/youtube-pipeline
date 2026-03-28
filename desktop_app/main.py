#!/usr/bin/env python3
"""
Desktop Application Wrapper for YouTube Video Generator
Packages the pipeline with a built-in web UI for easy distribution.
"""

import os
import sys
import json
import subprocess
import threading
import webbrowser
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socketserver

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline import YouTubePipeline
from content_generator import ContentGenerator

class DesktopApp:
    """Desktop application wrapper."""
    
    def __init__(self):
        self.port = 0  # Auto-find port
        self.server = None
        self.thread = None
        
    def find_free_port(self):
        """Find a free port."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def start_web_ui(self):
        """Start built-in web UI."""
        self.port = self.find_free_port()
        
        ui_dir = PROJECT_ROOT / "desktop_app" / "ui"
        ui_dir.mkdir(parents=True, exist_ok=True)
        
        # Create index.html if not exists
        self._create_ui_files(ui_dir)
        
        os.chdir(ui_dir)
        
        handler = SimpleHTTPRequestHandler
        self.server = socketserver.TCPServer(("", self.port), handler)
        
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        
        print(f"Web UI started on http://localhost:{self.port}")
        webbrowser.open(f"http://localhost:{self.port}")
    
    def _create_ui_files(self, ui_dir):
        """Create UI files."""
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Video Generator</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: white; text-align: center; margin-bottom: 30px; font-size: 2.2rem; }
        .card {
            background: white;
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            margin-bottom: 30px;
        }
        .form-group { margin-bottom: 20px; }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #444;
            font-size: 14px;
            text-transform: uppercase;
        }
        input, select, textarea {
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 16px;
            transition: all 0.3s;
        }
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        textarea { min-height: 100px; resize: vertical; }
        .row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .checkbox-group { display: flex; gap: 25px; flex-wrap: wrap; margin-top: 10px; }
        .checkbox-item { display: flex; align-items: center; gap: 8px; }
        .checkbox-item input { width: 20px; height: 20px; }
        .btn {
            width: 100%;
            padding: 18px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .progress { display: none; margin-top: 30px; }
        .progress.active { display: block; }
        .progress-bar {
            height: 10px;
            background: #e0e0e0;
            border-radius: 5px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            transition: width 0.5s;
            width: 0%;
        }
        .terminal {
            background: #1e1e2e;
            color: #cdd6f4;
            padding: 20px;
            border-radius: 12px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            min-height: 200px;
            max-height: 300px;
            overflow-y: auto;
            margin-top: 20px;
            line-height: 1.6;
        }
        .terminal-line { margin: 2px 0; }
        .terminal-line.error { color: #f38ba8; }
        .terminal-line.success { color: #a6e3a1; }
        .result {
            margin-top: 20px;
            padding: 20px;
            border-radius: 12px;
            display: none;
        }
        .result.active { display: block; }
        .result.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .result.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .videos-section { margin-top: 30px; }
        .videos-section h2 { color: white; margin-bottom: 20px; }
        .video-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
        }
        .video-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }
        .video-name { font-weight: 600; margin-bottom: 8px; word-break: break-all; }
        .video-meta { font-size: 13px; color: #666; margin-bottom: 15px; }
        .btn-small {
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        .btn-small:hover { background: #5a6fd6; }
        .spinner {
            display: inline-block;
            width: 18px;
            height: 18px;
            border: 2px solid white;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <h1>YouTube Video Generator</h1>
        
        <div class="card">
            <form id="generateForm">
                <div class="form-group">
                    <label for="topic">Video Topic *</label>
                    <input type="text" id="topic" placeholder="e.g., The History of Space Exploration" required>
                </div>
                
                <div class="row">
                    <div class="form-group">
                        <label for="duration">Duration (seconds)</label>
                        <input type="number" id="duration" value="60" min="30" max="300">
                    </div>
                    <div class="form-group">
                        <label for="theme">Visual Theme</label>
                        <select id="theme">
                            <option value="modern">Modern</option>
                            <option value="minimal">Minimal</option>
                            <option value="vibrant">Vibrant</option>
                            <option value="corporate">Corporate</option>
                            <option value="cinematic">Cinematic</option>
                        </select>
                    </div>
                </div>
                
                <div class="row">
                    <div class="form-group">
                        <label for="style">Content Style</label>
                        <select id="style">
                            <option value="educational">Educational</option>
                            <option value="entertainment">Entertainment</option>
                            <option value="documentary">Documentary</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Options</label>
                        <div class="checkbox-group">
                            <div class="checkbox-item">
                                <input type="checkbox" id="music" checked>
                                <label for="music">Music</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="images" checked>
                                <label for="images">Images</label>
                            </div>
                            <div class="checkbox-item">
                                <input type="checkbox" id="upload">
                                <label for="upload">Upload</label>
                            </div>
                        </div>
                    </div>
                </div>
                
                <button type="submit" class="btn" id="submitBtn">Generate Video</button>
            </form>
            
            <div class="progress" id="progress">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
                <div class="terminal" id="terminal"></div>
            </div>
            
            <div class="result" id="result"></div>
        </div>
        
        <div class="videos-section">
            <h2>Generated Videos</h2>
            <div class="video-grid" id="videoGrid"></div>
        </div>
    </div>

    <script>
        const API_BASE = 'http://localhost:7777';
        
        const form = document.getElementById('generateForm');
        const submitBtn = document.getElementById('submitBtn');
        const progress = document.getElementById('progress');
        const progressFill = document.getElementById('progressFill');
        const terminal = document.getElementById('terminal');
        const result = document.getElementById('result');
        
        let isGenerating = false;
        let eventSource = null;
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (isGenerating) return;
            
            isGenerating = true;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner"></span>Generating...';
            progress.classList.add('active');
            terminal.innerHTML = '';
            result.className = 'result';
            result.innerHTML = '';
            progressFill.style.width = '5%';
            
            const data = {
                topic: document.getElementById('topic').value,
                duration: parseInt(document.getElementById('duration').value),
                style: document.getElementById('style').value,
                theme: document.getElementById('theme').value,
                music: document.getElementById('music').checked,
                images: document.getElementById('images').checked,
                upload: document.getElementById('upload').checked
            };
            
            // Start generation
            try {
                const response = await fetch(`${API_BASE}/generate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                if (!response.ok) throw new Error('Failed to start generation');
                
                // Connect to SSE for progress
                const jobId = await response.text();
                connectToProgress(jobId);
                
            } catch (err) {
                showError(err.message);
                resetForm();
            }
        });
        
        function connectToProgress(jobId) {
            eventSource = new EventSource(`${API_BASE}/progress/${jobId}`);
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'output') {
                    addTerminalLine(data.text);
                    updateProgress(data.text);
                } else if (data.type === 'complete') {
                    showSuccess(data.result);
                    eventSource.close();
                    resetForm();
                    loadVideos();
                } else if (data.type === 'error') {
                    showError(data.error);
                    eventSource.close();
                    resetForm();
                }
            };
            
            eventSource.onerror = () => {
                eventSource.close();
            };
        }
        
        function addTerminalLine(text) {
            const line = document.createElement('div');
            line.className = 'terminal-line';
            if (text.includes('Error')) line.classList.add('error');
            if (text.includes('DONE')) line.classList.add('success');
            line.textContent = text;
            terminal.appendChild(line);
            terminal.scrollTop = terminal.scrollHeight;
        }
        
        function updateProgress(text) {
            if (text.includes('[1/4]')) progressFill.style.width = '15%';
            else if (text.includes('[2/4]')) progressFill.style.width = '40%';
            else if (text.includes('[3/4]')) progressFill.style.width = '65%';
            else if (text.includes('[4/4]')) progressFill.style.width = '85%';
            else if (text.includes('DONE')) progressFill.style.width = '100%';
        }
        
        function showSuccess(result) {
            result.className = 'result success active';
            result.innerHTML = `<strong>Video generated!</strong><br>${result}`;
        }
        
        function showError(error) {
            result.className = 'result error active';
            result.innerHTML = `<strong>Error:</strong> ${error}`;
        }
        
        function resetForm() {
            isGenerating = false;
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Generate Video';
        }
        
        async function loadVideos() {
            try {
                const response = await fetch(`${API_BASE}/videos`);
                const videos = await response.json();
                
                const grid = document.getElementById('videoGrid');
                if (videos.length === 0) {
                    grid.innerHTML = '<p style="color:white">No videos yet</p>';
                    return;
                }
                
                grid.innerHTML = videos.map(v => {
                    const size = (v.size / 1024 / 1024).toFixed(1);
                    return `
                        <div class="video-card">
                            <div class="video-name">${v.name}</div>
                            <div class="video-meta">${size} MB • ${v.date}</div>
                            <button class="btn-small" onclick="openVideo('${v.path}')">Open</button>
                        </div>
                    `;
                }).join('');
            } catch (e) {
                console.error('Failed to load videos:', e);
            }
        }
        
        async function openVideo(path) {
            await fetch(`${API_BASE}/open`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path })
            });
        }
        
        loadVideos();
    </script>
</body>
</html>'''
        
        (ui_dir / 'index.html').write_text(html)
    
    def run(self):
        """Run the desktop application."""
        self.start_web_ui()
        
        # Keep main thread alive
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            if self.server:
                self.server.shutdown()

def main():
    """Main entry point."""
    app = DesktopApp()
    app.run()

if __name__ == "__main__":
    main()
