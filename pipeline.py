#!/usr/bin/env python3
"""Simplified YouTube content creation pipeline."""

import os
import asyncio
import json
import random
import argparse
import time
from pathlib import Path
from typing import Optional, List

from content_generator import ContentGenerator
from media_generator import MediaGenerator
from video_assembler import VideoAssembler
from youtube_uploader import YouTubeUploader
from image_generator import FreeImageGenerator


class YouTubePipeline:
    """Simplified end-to-end pipeline for YouTube video creation."""
    
    def __init__(self, 
                 provider_name: Optional[str] = None,
                 client_secrets: str = "client_secrets.json",
                 output_dir: str = "output",
                 temp_dir: str = "temp",
                 theme: str = "modern"):
        
        self.content_gen = ContentGenerator(provider_name=provider_name)
        self.media_gen = MediaGenerator(output_dir=temp_dir)
        self.video_asm = VideoAssembler(output_dir=output_dir, theme=theme)
        self.image_gen = FreeImageGenerator(output_dir=temp_dir + "/images")
        self.uploader = YouTubeUploader(client_secrets=client_secrets)
        self.theme = theme
        
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        
        # Create assets folder for music
        self.assets_dir = Path("assets")
        self.music_dir = self.assets_dir / "music"
        self.music_dir.mkdir(parents=True, exist_ok=True)
    
    async def create_video(self, 
                          topic: str,
                          duration: int = 60,
                          style: str = "educational",
                          theme: Optional[str] = None,
                          music_enabled: bool = True,
                          images_enabled: bool = True,
                          upload: bool = False,
                          privacy: str = "private") -> dict:
        """Run the full pipeline: script → TTS → images → video → upload."""
        
        theme = theme or self.theme
        self.video_asm.set_theme(theme)
        
        print(f"\n{'='*60}")
        print(f"Creating: {topic}")
        print(f"{'='*60}\n")
        
        # Step 1: Generate content
        print("[1/4] Generating script...")
        content = self.content_gen.generate_script(
            topic=topic,
            duration_seconds=duration,
            style=style
        )
        print(f"  Title: {content['title']}")
        print(f"  Segments: {len(content['segments'])}")
        
        # Save content
        content_path = self.output_dir / "content.json"
        with open(content_path, 'w') as f:
            json.dump(content, f, indent=2)
        
        # Step 2: Generate audio (TTS)
        print("\n[2/4] Generating audio (Edge TTS)...")
        audio_paths = []
        for i, segment in enumerate(content['segments']):
            text = segment.get("text", "")
            if text:
                audio_path = await self.media_gen.generate_speech(text)
                audio_paths.append(audio_path)
                print(f"  Segment {i+1}: {audio_path.name}")
        print(f"  Generated {len(audio_paths)} audio files")
        
        # Validate we have audio before proceeding
        if not audio_paths:
            raise ValueError("No audio files generated. TTS failed for all segments.")
        
        # Step 3: Generate images
        image_paths = []
        if images_enabled:
            print("\n[3/4] Generating images (Pollinations AI)...")
            for i, segment in enumerate(content['segments']):
                seg_type = segment.get("type", "content")
                if seg_type == "content":
                    visual = segment.get("visual_suggestion", "")
                    text = segment.get("text", "")
                    img_path = self.image_gen.generate_image(
                        prompt=visual or text[:100],
                        output_path=str(self.temp_dir / f"img_{i:03d}.png")
                    )
                    image_paths.append(img_path)
                    if img_path:
                        print(f"  Scene {i}: Generated")
                    else:
                        print(f"  Scene {i}: Skipped (no image)")
                else:
                    image_paths.append(None)
        
        # Step 4: Assemble video
        print("\n[4/4] Assembling video...")
        # Add timestamp to prevent filename collisions
        timestamp = int(time.time())
        video_path = self.output_dir / f"{self._sanitize_filename(content['title'])}_{timestamp}.mp4"
        
        self.video_asm.assemble_video(
            segments=content['segments'],
            audio_paths=[str(p) for p in audio_paths],
            image_paths=image_paths,
            output_path=str(video_path)
        )
        print(f"  Video: {video_path}")
        
        # Add background music from assets folder
        if music_enabled:
            video_path = self._add_background_music(video_path)
        
        # Create thumbnail
        thumb_path = self.output_dir / f"{self._sanitize_filename(content['title'])}_{timestamp}_thumb.jpg"
        self.video_asm.create_thumbnail(
            title=content['title'],
            output_path=str(thumb_path)
        )
        print(f"  Thumbnail: {thumb_path}")
        
        result = {
            "topic": topic,
            "title": content['title'],
            "description": content['description'],
            "tags": content['tags'],
            "video_path": str(video_path),
            "thumbnail_path": str(thumb_path),
            "uploaded": False,
            "video_id": None
        }
        
        # Upload to YouTube
        if upload:
            print("\n[UPLOAD] Uploading to YouTube...")
            video_id = self.uploader.upload_video(
                video_path=str(video_path),
                title=content['title'],
                description=content['description'],
                tags=content['tags'],
                privacy=privacy
            )
            
            if video_id:
                result['uploaded'] = True
                result['video_id'] = video_id
                result['video_url'] = f"https://youtube.com/watch?v={video_id}"
                self.uploader.set_thumbnail(video_id, str(thumb_path))
        
        # Save result
        with open(self.output_dir / "result.json", 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\n{'='*60}")
        print(f"DONE: {video_path}")
        print(f"{'='*60}\n")
        
        return result
    
    def _add_background_music(self, video_path: Path) -> Path:
        """Add royalty-free music from assets/music folder."""
        music_files = list(self.music_dir.glob("*.mp3")) + list(self.music_dir.glob("*.wav"))
        
        if not music_files:
            print("  No music in assets/music/ - skipping background music")
            print("  Add .mp3/.wav files to assets/music/ to auto-include")
            return video_path
        
        # Pick random track
        music_file = random.choice(music_files)
        print(f"  Adding music: {music_file.name}")
        
        from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip
        
        video = VideoFileClip(str(video_path))
        music = AudioFileClip(str(music_file))
        music = music.with_volume_scaled(0.3)  # 30% volume
        
        # Loop if needed
        if music.duration < video.duration:
            music = music.loop(duration=video.duration)
        else:
            music = music.subclip(0, video.duration)
        
        # Mix with existing audio
        if video.audio:
            composite = CompositeAudioClip([video.audio, music])
        else:
            composite = music
        
        final = video.set_audio(composite)
        output_path = video_path.parent / f"{video_path.stem}_with_music.mp4"
        
        final.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            logger=None
        )
        
        video.close()
        music.close()
        
        return output_path
    
    def _sanitize_filename(self, filename: str) -> str:
        """Create safe filename, prevent path traversal."""
        import re
        if not filename:
            return "video"
        
        # Remove path traversal attempts
        filename = filename.replace('..', '')
        filename = filename.replace('/', '')
        filename = filename.replace('\\', '')
        
        # Remove other unsafe characters
        safe = re.sub(r'[^\w\s-]', '', filename).strip().lower()
        safe = re.sub(r'[-\s]+', '-', safe)
        return safe[:50] or "video"


def main():
    parser = argparse.ArgumentParser(description="YouTube Video Generator")
    parser.add_argument("--topic", default=None, help="Video topic (or will prompt)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--style", default="educational", help="Content style")
    parser.add_argument("--theme", default="modern", 
                       choices=["modern", "minimal", "vibrant", "corporate", "cinematic"],
                       help="Visual theme")
    parser.add_argument("--provider", default=None, help="LLM provider")
    parser.add_argument("--music", action="store_true", default=True, help="Add background music")
    parser.add_argument("--no-music", dest="music", action="store_false", help="No music")
    parser.add_argument("--images", action="store_true", default=True, help="Generate images")
    parser.add_argument("--no-images", dest="images", action="store_false", help="No images")
    parser.add_argument("--upload", action="store_true", help="Upload to YouTube")
    parser.add_argument("--privacy", default="private", 
                       choices=["private", "unlisted", "public"],
                       help="Upload privacy")
    
    args = parser.parse_args()
    
    # Prompt for topic if not provided
    topic = args.topic
    if not topic:
        topic = input("Enter video topic: ").strip()
        if not topic:
            print("Error: Topic is required")
            return
    
    pipeline = YouTubePipeline(
        provider_name=args.provider,
        theme=args.theme
    )
    
    result = asyncio.run(pipeline.create_video(
        topic=topic,
        duration=args.duration,
        style=args.style,
        theme=args.theme,
        music_enabled=args.music,
        images_enabled=args.images,
        upload=args.upload,
        privacy=args.privacy
    ))
    
    print(f"Video: {result['video_path']}")
    if result['uploaded']:
        print(f"YouTube: {result['video_url']}")


if __name__ == "__main__":
    main()
