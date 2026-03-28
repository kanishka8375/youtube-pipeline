#!/usr/bin/env python3
"""
Backend API server for desktop application.
Handles generation requests and streams progress.
"""

import os
import sys
import json
import uuid
import asyncio
import subprocess
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import time

PROJECT_ROOT = Path(__file__).parent.parent

# Store jobs
jobs = {}

class APIHandler(BaseHTTPRequestHandler):
    """HTTP API handler."""
    
    def log_message(self, format, *args):
        pass  # Suppress logs
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/videos':
            self.send_json(self.get_videos())
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        if self.path == '/generate':
            data = json.loads(body)
            job_id = self.start_generation(data)
            self.send_text(job_id)
        elif self.path == '/open':
            data = json.loads(body)
            self.open_file(data['path'])
            self.send_json({'ok': True})
        else:
            self.send_error(404)
    
    def start_generation(self, data):
        """Start video generation in background."""
        job_id = str(uuid.uuid4())[:8]
        
        jobs[job_id] = {
            'status': 'running',
            'output': [],
            'result': None
        }
        
        def run():
            args = [
                'python3', str(PROJECT_ROOT / 'pipeline.py'),
                '--topic', data['topic'],
                '--duration', str(data['duration']),
                '--style', data['style'],
                '--theme', data['theme']
            ]
            
            if data.get('music'):
                args.append('--music')
            else:
                args.append('--no-music')
            
            if data.get('images'):
                args.append('--images')
            else:
                args.append('--no-images')
            
            if data.get('upload'):
                args.append('--upload')
            
            env = os.environ.copy()
            home = os.path.expanduser('~')
            env['PYTHONPATH'] = f"{home}/.local/lib/python3.12/site-packages"
            
            process = subprocess.Popen(
                args,
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
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
        
        Thread(target=run, daemon=True).start()
        return job_id
    
    def get_videos(self):
        """Get list of generated videos."""
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
        """Open file with default application."""
        import platform
        system = platform.system()
        
        if system == 'Darwin':
            subprocess.run(['open', path])
        elif system == 'Windows':
            subprocess.run(['start', '', path], shell=True)
        else:
            subprocess.run(['xdg-open', path])
    
    def send_json(self, data):
        """Send JSON response."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_text(self, text):
        """Send text response."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(text.encode())

class ProgressHandler(BaseHTTPRequestHandler):
    """SSE handler for progress updates."""
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        """Handle SSE connection."""
        if not self.path.startswith('/progress/'):
            self.send_error(404)
            return
        
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
            
            # Send new output lines
            while last_index < len(job['output']):
                line = job['output'][last_index]
                data = json.dumps({'type': 'output', 'text': line})
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                last_index += 1
            
            # Check if complete
            if job['status'] == 'complete':
                data = json.dumps({'type': 'complete', 'result': job.get('result')})
                self.wfile.write(f"data: {data}\n\n".encode())
                break
            elif job['status'] == 'error':
                data = json.dumps({'type': 'error', 'error': job.get('error')})
                self.wfile.write(f"data: {data}\n\n".encode())
                break
            
            time.sleep(0.1)

def start_api_server(port=7777):
    """Start the API server."""
    server = HTTPServer(('localhost', port), APIHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"API server started on http://localhost:{port}")
    return server

def start_progress_server(port=7778):
    """Start the progress SSE server."""
    server = HTTPServer(('localhost', port), ProgressHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Progress server started on http://localhost:{port}")
    return server

if __name__ == '__main__':
    start_api_server()
    start_progress_server()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
