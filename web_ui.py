"""Simple web UI for YouTube video generator."""

import os
import asyncio
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS

from pipeline import YouTubePipeline

app = Flask(__name__)
CORS(app)

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Store job status
jobs = {}


@app.route("/")
def index():
    """Serve the main UI."""
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    """Start video generation."""
    data = request.json or {}
    topic = data.get("topic", "").strip()
    
    if not topic:
        return jsonify({"error": "Topic required"}), 400
    
    job_id = f"job_{len(jobs)}"
    jobs[job_id] = {"status": "starting", "progress": 0, "result": None}
    
    # Run in background thread
    import threading
    
    def run_generation():
        try:
            jobs[job_id]["status"] = "generating"
            jobs[job_id]["progress"] = 10
            
            pipeline = YouTubePipeline(
                provider_name=data.get("provider"),
                theme=data.get("theme", "modern")
            )
            
            result = asyncio.run(pipeline.create_video(
                topic=topic,
                duration=data.get("duration", 60),
                style=data.get("style", "educational"),
                theme=data.get("theme", "modern"),
                music_enabled=data.get("music", True),
                images_enabled=data.get("images", True),
                upload=data.get("upload", False)
            ))
            
            jobs[job_id]["status"] = "complete"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["result"] = result
            
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)
    
    thread = threading.Thread(target=run_generation)
    thread.daemon = True
    thread.start()
    
    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/status/<job_id>")
def status(job_id):
    """Get job status."""
    job = jobs.get(job_id, {})
    return jsonify(job)


@app.route("/api/videos")
def list_videos():
    """List generated videos."""
    videos = []
    for f in OUTPUT_DIR.glob("*.mp4"):
        videos.append({
            "name": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime
        })
    return jsonify(sorted(videos, key=lambda x: x["modified"], reverse=True))


@app.route("/output/<path:filename>")
def serve_video(filename):
    """Serve video files."""
    return send_from_directory(OUTPUT_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
