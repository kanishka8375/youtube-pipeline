#!/usr/bin/env python3
"""
YouTube Video Generator - Desktop Application
Simple desktop wrapper using pywebview for cross-platform GUI.
"""

import os
import sys
import json
import uuid
import subprocess
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import time

# Detect if we're in a virtual environment
def get_venv_python():
    """Get the correct Python executable (venv if active)."""
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # In a venv, use current executable
        return sys.executable
    return sys.executable

def get_venv_pip():
    """Get the correct pip executable."""
    python = get_venv_python()
    return [python, "-m", "pip"]

VENV_PYTHON = get_venv_python()

# Try to import webview
try:
    import webview
except ImportError:
    print("pywebview not found. Installing...")
    try:
        subprocess.check_call(get_venv_pip() + ["install", "pywebview"], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import webview
        print("pywebview installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install pywebview: {e}")
        print("\nPlease install manually:")
        print(f"  {VENV_PYTHON} -m pip install pywebview")
        print("\nOr if using system packages:")
        print("  sudo apt install python3-webview")
        sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent
jobs = {}

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        if self.path == '/videos':
            self.send_json(self.get_videos())
        elif self.path.startswith('/progress/'):
            self.handle_progress()
        else:
            self.send_error(404)
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        if self.path == '/generate':
            data = json.loads(body)
            job_id = self.start_generation(data)
            self.send_json({'job_id': job_id})
        elif self.path == '/open':
            data = json.loads(body)
            self.open_file(data['path'])
            self.send_json({'ok': True})
        else:
            self.send_error(404)
    
    def handle_progress(self):
        """Handle SSE for progress."""
        job_id = self.path.split('/')[-1]
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        last_index = 0
        while True:
            if job_id not in jobs:
                break
            job = jobs[job_id]
            
            while last_index < len(job['output']):
                line = job['output'][last_index]
                data = json.dumps({'type': 'output', 'text': line})
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                last_index += 1
            
            if job['status'] == 'complete':
                data = json.dumps({'type': 'complete', 'result': job.get('result')})
                self.wfile.write(f"data: {data}\n\n".encode())
                break
            elif job['status'] == 'error':
                data = json.dumps({'type': 'error', 'error': job.get('error')})
                self.wfile.write(f"data: {data}\n\n".encode())
                break
            
            time.sleep(0.1)
    
    def start_generation(self, data):
        job_id = str(uuid.uuid4())[:8]
        jobs[job_id] = {'status': 'running', 'output': [], 'result': None}
        
        def run():
            args = [
                VENV_PYTHON, str(PROJECT_ROOT / 'pipeline.py'),
                '--topic', data['topic'],
                '--duration', str(data['duration']),
                '--style', data['style'],
                '--theme', data['theme']
            ]
            
            if data.get('music'): args.append('--music')
            else: args.append('--no-music')
            
            if data.get('images'): args.append('--images')
            else: args.append('--no-images')
            
            if data.get('upload'): args.append('--upload')
            
            env = os.environ.copy()
            home = os.path.expanduser('~')
            env['PYTHONPATH'] = f"{home}/.local/lib/python3.12/site-packages:{env.get('PYTHONPATH', '')}"
            
            try:
                process = subprocess.Popen(
                    args, cwd=str(PROJECT_ROOT), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, universal_newlines=True
                )
                
                for line in process.stdout:
                    jobs[job_id]['output'].append(line.strip())
                
                process.wait()
                
                if process.returncode == 0:
                    jobs[job_id]['status'] = 'complete'
                    jobs[job_id]['result'] = 'Video generated successfully'
                else:
                    jobs[job_id]['status'] = 'error'
                    jobs[job_id]['error'] = 'Generation failed'
            except Exception as e:
                jobs[job_id]['status'] = 'error'
                jobs[job_id]['error'] = str(e)
        
        threading.Thread(target=run, daemon=True).start()
        return job_id
    
    def get_videos(self):
        output_dir = PROJECT_ROOT / 'output'
        videos = []
        if output_dir.exists():
            for f in sorted(output_dir.glob('*.mp4'), key=lambda x: x.stat().st_mtime, reverse=True):
                stat = f.stat()
                videos.append({
                    'name': f.name,
                    'path': str(f),
                    'size': stat.st_size,
                    'date': time.ctime(stat.st_mtime)
                })
        return videos
    
    def open_file(self, path):
        import platform
        system = platform.system()
        if system == 'Darwin':
            subprocess.run(['open', path])
        elif system == 'Windows':
            os.startfile(path)
        else:
            subprocess.run(['xdg-open', path])
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

class DesktopApp:
    """Desktop application using pywebview."""
    
    def __init__(self):
        self.port = self._find_free_port()
        self.api_url = f"http://localhost:{self.port}"
        
    def _find_free_port(self):
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    
    def start_server(self):
        server = HTTPServer(('localhost', self.port), APIHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"API server: {self.api_url}")
    
    def create_ui(self):
        """Create the HTML UI."""
        ui_dir = PROJECT_ROOT / 'desktop_app' / 'ui'
        ui_dir.mkdir(parents=True, exist_ok=True)
        
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Video Generator</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ color: white; text-align: center; margin-bottom: 30px; font-size: 2.2rem; }}
        .card {{
            background: white;
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            margin-bottom: 30px;
        }}
        .form-group {{ margin-bottom: 20px; }}
        label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #444;
            font-size: 14px;
            text-transform: uppercase;
        }}
        input, select, textarea {{
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 16px;
            transition: all 0.3s;
        }}
        input:focus, select:focus {{ outline: none; border-color: #667eea; }}
        .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .checkbox-group {{ display: flex; gap: 25px; flex-wrap: wrap; margin-top: 10px; }}
        .checkbox-item {{ display: flex; align-items: center; gap: 8px; }}
        .checkbox-item input {{ width: 20px; height: 20px; }}
        .btn {{
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
        }}
        .btn:hover:not(:disabled) {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }}
        .btn:disabled {{ opacity: 0.6; cursor: not-allowed; }}
        .progress {{ display: none; margin-top: 30px; }}
        .progress.active {{ display: block; }}
        .progress-bar {{
            height: 10px;
            background: #e0e0e0;
            border-radius: 5px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            transition: width 0.5s;
            width: 0%;
        }}
        .terminal {{
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
        }}
        .terminal-line {{ margin: 2px 0; }}
        .terminal-line.error {{ color: #f38ba8; }}
        .terminal-line.success {{ color: #a6e3a1; }}
        .result {{
            margin-top: 20px;
            padding: 20px;
            border-radius: 12px;
            display: none;
        }}
        .result.active {{ display: block; }}
        .result.success {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
        .result.error {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        .videos-section {{ margin-top: 30px; }}
        .videos-section h2 {{ color: white; margin-bottom: 20px; }}
        .video-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
        }}
        .video-card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }}
        .video-name {{ font-weight: 600; margin-bottom: 8px; word-break: break-all; }}
        .video-meta {{ font-size: 13px; color: #666; margin-bottom: 15px; }}
        .btn-small {{
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }}
        .spinner {{
            display: inline-block;
            width: 18px;
            height: 18px;
            border: 2px solid white;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
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
        const API_BASE = '{self.api_url}';
        
        const form = document.getElementById('generateForm');
        const submitBtn = document.getElementById('submitBtn');
        const progress = document.getElementById('progress');
        const progressFill = document.getElementById('progressFill');
        const terminal = document.getElementById('terminal');
        const result = document.getElementById('result');
        
        let isGenerating = false;
        
        form.addEventListener('submit', async (e) => {{
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
            
            const data = {{
                topic: document.getElementById('topic').value,
                duration: parseInt(document.getElementById('duration').value),
                style: document.getElementById('style').value,
                theme: document.getElementById('theme').value,
                music: document.getElementById('music').checked,
                images: document.getElementById('images').checked,
                upload: document.getElementById('upload').checked
            }};
            
            try {{
                const response = await fetch(`${{API_BASE}}/generate`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(data)
                }});
                
                const {{job_id}} = await response.json();
                
                // Connect to SSE
                const evtSource = new EventSource(`${{API_BASE}}/progress/${{job_id}}`);
                
                evtSource.onmessage = (event) => {{
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'output') {{
                        const line = document.createElement('div');
                        line.className = 'terminal-line';
                        if (data.text.includes('Error')) line.classList.add('error');
                        if (data.text.includes('DONE')) line.classList.add('success');
                        line.textContent = data.text;
                        terminal.appendChild(line);
                        terminal.scrollTop = terminal.scrollHeight;
                        
                        if (data.text.includes('[1/4]')) progressFill.style.width = '15%';
                        else if (data.text.includes('[2/4]')) progressFill.style.width = '40%';
                        else if (data.text.includes('[3/4]')) progressFill.style.width = '65%';
                        else if (data.text.includes('[4/4]')) progressFill.style.width = '85%';
                        else if (data.text.includes('DONE')) progressFill.style.width = '100%';
                    }} else if (data.type === 'complete') {{
                        result.className = 'result success active';
                        result.innerHTML = '<strong>Video generated successfully!</strong>';
                        evtSource.close();
                        resetForm();
                        loadVideos();
                    }} else if (data.type === 'error') {{
                        result.className = 'result error active';
                        result.innerHTML = `<strong>Error:</strong> ${{data.error}}`;
                        evtSource.close();
                        resetForm();
                    }}
                }};
                
            }} catch (err) {{
                result.className = 'result error active';
                result.innerHTML = `<strong>Error:</strong> ${{err.message}}`;
                resetForm();
            }}
        }});
        
        function resetForm() {{
            isGenerating = false;
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Generate Video';
        }}
        
        async function loadVideos() {{
            try {{
                const response = await fetch(`${{API_BASE}}/videos`);
                const videos = await response.json();
                
                const grid = document.getElementById('videoGrid');
                if (videos.length === 0) {{
                    grid.innerHTML = '<p style="color:white">No videos yet</p>';
                    return;
                }}
                
                grid.innerHTML = videos.map(v => {{
                    const size = (v.size / 1024 / 1024).toFixed(1);
                    return `
                        <div class="video-card">
                            <div class="video-name">${{v.name}}</div>
                            <div class="video-meta">${{size}} MB • ${{v.date}}</div>
                            <button class="btn-small" onclick="openVideo('${{v.path}}')">Open</button>
                        </div>
                    `;
                }}).join('');
            }} catch (e) {{ console.error(e); }}
        }}
        
        async function openVideo(path) {{
            await fetch(`${{API_BASE}}/open`, {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{path}})
            }});
        }}
        
        loadVideos();
    </script>
</body>
</html>'''
        
        (ui_dir / 'index.html').write_text(html)
        return ui_dir / 'index.html'
    
    def run(self):
        """Run the desktop application."""
        print("Starting YouTube Video Generator Desktop App...")
        
        # Start API server
        self.start_server()
        
        # Create UI
        ui_file = self.create_ui()
        
        # Open in webview
        webview.create_window(
            'YouTube Video Generator',
            str(ui_file),
            width=1200,
            height=800,
            min_size=(900, 600),
            resizable=True
        )
        webview.start()

def main():
    app = DesktopApp()
    app.run()

if __name__ == '__main__':
    main()
