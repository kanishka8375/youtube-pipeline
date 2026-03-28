"""Simple web UI for YouTube Pipeline control."""

import os
import asyncio
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS

from pipeline import YouTubePipeline
from llm_providers import LLMProviderFactory
from video_effects import VideoConfig, AspectRatio, get_preset

app = Flask(__name__)
CORS(app)

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Store active jobs
active_jobs = {}
batch_jobs = {}


@app.route("/")
def index():
    """Main dashboard."""
    providers = LLMProviderFactory.list_available()
    return render_template("index.html", providers=providers)


@app.route("/api/providers")
def get_providers():
    """Get available LLM providers."""
    return jsonify({
        "available": LLMProviderFactory.list_available(),
        "all": ["ollama", "groq", "gemini"]
    })


@app.route("/api/generate", methods=["POST"])
def generate_video():
    """Start video generation with advanced options."""
    data = request.json
    
    topic = data.get("topic", "")
    duration = int(data.get("duration", 60))
    style = data.get("style", "educational")
    provider = data.get("provider", "auto")
    theme = data.get("theme", "modern")
    
    if not topic:
        return jsonify({"error": "Topic is required"}), 400
    
    job_id = f"job_{hash(topic + str(duration)) % 100000:05d}"
    
    def run_pipeline():
        try:
            active_jobs[job_id] = {"status": "running", "progress": 0}
            
            # Build video configuration from request
            video_preset = data.get("video_preset")
            
            if video_preset:
                # Use preset configuration
                video_config = get_preset(video_preset)
            else:
                # Build custom config
                aspect_ratio_str = data.get("aspect_ratio", "16:9")
                ratio_map = {
                    "16:9": AspectRatio.LANDSCAPE_16_9,
                    "9:16": AspectRatio.PORTRAIT_9_16,
                    "1:1": AspectRatio.SQUARE_1_1,
                    "4:3": AspectRatio.CLASSIC_4_3,
                    "21:9": AspectRatio.CINEMATIC_21_9
                }
                ar = ratio_map.get(aspect_ratio_str, AspectRatio.LANDSCAPE_16_9)
                
                video_config = VideoConfig(
                    aspect_ratio=ar,
                    quality_preset=data.get("quality", "high"),
                    enable_transitions=data.get("transition_type", "fade") != "none",
                    transition_type=data.get("transition_type", "fade"),
                    enable_captions=data.get("captions", False),
                    enable_ken_burns=data.get("ken_burns", False),
                    color_grading=data.get("color_grading") or None,
                    enable_text_animations=data.get("text_animation", "fade") != "none",
                    text_animation=data.get("text_animation", "fade")
                )
            
            # Create pipeline with video config
            pipeline = YouTubePipeline(
                provider_name=provider if provider != "auto" else None,
                theme=theme,
                music_enabled=data.get("music", True),
                images_enabled=data.get("images", True),
                video_config=video_config
            )
            
            # Update progress
            active_jobs[job_id]["progress"] = 10
            active_jobs[job_id]["status"] = "generating content..."
            
            result = asyncio.run(pipeline.create_video(
                topic=topic,
                duration=duration,
                style=style,
                theme=theme,
                music_genre=data.get("music_genre", "ambient"),
                music_mood=data.get("music_mood", "calm"),
                music_enabled=data.get("music", True),
                images_enabled=data.get("images", True),
                upload=False
            ))
            
            active_jobs[job_id] = {
                "status": "complete",
                "progress": 100,
                "result": result
            }
            
        except Exception as e:
            active_jobs[job_id] = {"status": "error", "error": str(e)}
    
    # Run in background
    import threading
    thread = threading.Thread(target=run_pipeline)
    thread.start()
    
    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/job/<job_id>")
def get_job_status(job_id):
    """Get job status."""
    job = active_jobs.get(job_id, {"status": "not_found"})
    return jsonify(job)


@app.route("/api/videos")
def list_videos():
    """List generated videos."""
    videos = []
    for file in OUTPUT_DIR.glob("*.mp4"):
        thumb = file.with_suffix(".jpg")
        if not thumb.exists():
            thumb = file.with_suffix("_thumb.jpg")
        
        videos.append({
            "name": file.name,
            "path": str(file),
            "thumbnail": str(thumb) if thumb.exists() else None,
            "created": file.stat().st_mtime
        })
    
    videos.sort(key=lambda x: x["created"], reverse=True)
    return jsonify(videos)


@app.route("/api/videos/<path:filename>")
def serve_video(filename):
    """Serve video file."""
    return send_from_directory(OUTPUT_DIR, filename)


@app.route("/api/batch", methods=["POST"])
def create_batch_job():
    """Create a batch processing job with multiple videos."""
    data = request.json
    
    videos = data.get("videos", [])
    if not videos or not isinstance(videos, list):
        return jsonify({"error": "Videos array is required"}), 400
    
    batch_id = f"batch_{hash(str(videos)) % 100000:05d}"
    
    batch_jobs[batch_id] = {
        "status": "queued",
        "total": len(videos),
        "completed": 0,
        "failed": 0,
        "results": [],
        "videos": videos
    }
    
    def run_batch():
        batch_jobs[batch_id]["status"] = "running"
        
        for i, video_config in enumerate(videos):
            try:
                # Build video config
                video_preset = video_config.get("video_preset")
                if video_preset:
                    config = get_preset(video_preset)
                else:
                    ar_str = video_config.get("aspect_ratio", "16:9")
                    ratio_map = {
                        "16:9": AspectRatio.LANDSCAPE_16_9,
                        "9:16": AspectRatio.PORTRAIT_9_16,
                        "1:1": AspectRatio.SQUARE_1_1,
                        "4:3": AspectRatio.CLASSIC_4_3,
                        "21:9": AspectRatio.CINEMATIC_21_9
                    }
                    ar = ratio_map.get(ar_str, AspectRatio.LANDSCAPE_16_9)
                    config = VideoConfig(
                        aspect_ratio=ar,
                        quality_preset=video_config.get("quality", "high"),
                        enable_transitions=video_config.get("transition_type", "fade") != "none",
                        transition_type=video_config.get("transition_type", "fade"),
                        enable_captions=video_config.get("captions", False),
                        enable_ken_burns=video_config.get("ken_burns", False),
                        color_grading=video_config.get("color_grading") or None,
                        enable_text_animations=video_config.get("text_animation", "fade") != "none",
                        text_animation=video_config.get("text_animation", "fade")
                    )
                
                # Create pipeline
                pipeline = YouTubePipeline(
                    provider_name=video_config.get("provider") if video_config.get("provider") != "auto" else None,
                    theme=video_config.get("theme", "modern"),
                    music_enabled=video_config.get("music", True),
                    images_enabled=video_config.get("images", True),
                    video_config=config
                )
                
                # Generate video
                result = asyncio.run(pipeline.create_video(
                    topic=video_config["topic"],
                    duration=int(video_config.get("duration", 60)),
                    style=video_config.get("style", "educational"),
                    theme=video_config.get("theme", "modern"),
                    music_genre=video_config.get("music_genre", "ambient"),
                    music_mood=video_config.get("music_mood", "calm"),
                    music_enabled=video_config.get("music", True),
                    images_enabled=video_config.get("images", True),
                    upload=False
                ))
                
                batch_jobs[batch_id]["results"].append({
                    "index": i,
                    "topic": video_config["topic"],
                    "status": "complete",
                    "video_path": result["video_path"]
                })
                batch_jobs[batch_id]["completed"] += 1
                
            except Exception as e:
                batch_jobs[batch_id]["results"].append({
                    "index": i,
                    "topic": video_config.get("topic", "unknown"),
                    "status": "error",
                    "error": str(e)
                })
                batch_jobs[batch_id]["failed"] += 1
        
        batch_jobs[batch_id]["status"] = "complete"
    
    # Run batch in background
    import threading
    thread = threading.Thread(target=run_batch)
    thread.start()
    
    return jsonify({"batch_id": batch_id, "status": "started", "total": len(videos)})


@app.route("/api/batch/<batch_id>")
def get_batch_status(batch_id):
    """Get batch job status."""
    job = batch_jobs.get(batch_id, {"status": "not_found"})
    return jsonify(job)


@app.route("/api/batches")
def list_batches():
    """List all batch jobs."""
    return jsonify({
        batch_id: {
            "status": job["status"],
            "total": job["total"],
            "completed": job.get("completed", 0),
            "failed": job.get("failed", 0)
        }
        for batch_id, job in batch_jobs.items()
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
