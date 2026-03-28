#!/usr/bin/env python3
"""Main YouTube content creation pipeline orchestrator."""

import os
import asyncio
import json
import argparse
from pathlib import Path
from typing import Optional

from content_generator import ContentGenerator
from media_generator import MediaGenerator
from video_assembler import VideoAssembler
from youtube_uploader import YouTubeUploader
from music_generator import FreeMusicGenerator, MusicConfig
from image_generator import FreeImageGenerator
from sync_engine import SyncEngine, SyncConfig
from validators import ContentValidator, ValidationRetryManager
from video_effects import VideoConfig, get_preset, AspectRatio


class YouTubePipeline:
    """End-to-end pipeline for automated YouTube video creation."""
    
    def __init__(self, 
                 provider_name: Optional[str] = None,
                 client_secrets: str = "client_secrets.json",
                 output_dir: str = "output",
                 temp_dir: str = "temp",
                 theme: str = "modern",
                 music_enabled: bool = True,
                 images_enabled: bool = True,
                 sync_config: Optional[SyncConfig] = None,
                 validation_enabled: bool = True,
                 max_retries: int = 3,
                 aspect_ratio: str = "16:9",
                 video_preset: Optional[str] = None,
                 video_config: Optional[VideoConfig] = None):
        
        # Video configuration - use preset or create from parameters
        if video_config:
            self.video_config = video_config
        elif video_preset:
            self.video_config = get_preset(video_preset)
        else:
            # Create config from aspect ratio
            ratio_map = {
                "16:9": AspectRatio.LANDSCAPE_16_9,
                "9:16": AspectRatio.PORTRAIT_9_16,
                "1:1": AspectRatio.SQUARE_1_1,
                "4:3": AspectRatio.CLASSIC_4_3,
                "21:9": AspectRatio.CINEMATIC_21_9
            }
            ar = ratio_map.get(aspect_ratio, AspectRatio.LANDSCAPE_16_9)
            self.video_config = VideoConfig(aspect_ratio=ar)
        
        self.content_gen = ContentGenerator(provider_name=provider_name)
        self.media_gen = MediaGenerator(output_dir=temp_dir)
        self.video_asm = VideoAssembler(output_dir=output_dir, theme=theme, video_config=self.video_config)
        self.music_gen = FreeMusicGenerator(output_dir=temp_dir + "/music") if music_enabled else None
        self.image_gen = FreeImageGenerator(output_dir=temp_dir + "/images") if images_enabled else None
        self.sync_engine = SyncEngine(config=sync_config)
        self.uploader = YouTubeUploader(client_secrets=client_secrets)
        self.theme = theme
        
        # Validation system
        self.validation_enabled = validation_enabled
        self.validator = ContentValidator(llm_provider=self.content_gen.provider if validation_enabled else None)
        self.retry_manager = ValidationRetryManager(max_retries=max_retries)
        
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
    
    async def create_video(self, 
                          topic: str,
                          duration: int = 60,
                          style: str = "educational",
                          theme: Optional[str] = None,
                          music_genre: str = "ambient",
                          music_mood: str = "calm",
                          music_enabled: bool = True,
                          images_enabled: bool = True,
                          upload: bool = False,
                          privacy: str = "private") -> dict:
        """Run the full pipeline to create and optionally upload a video."""
        
        # Use instance theme if not specified
        theme = theme or self.theme
        self.video_asm.set_theme(theme)
        
        print(f"\n{'='*60}")
        print(f"PIPELINE START: {topic}")
        print(f"Theme: {theme}")
        if music_enabled and self.music_gen:
            print(f"Music: {music_genre} ({music_mood})")
        if images_enabled and self.image_gen:
            print(f"Images: AI-generated per scene")
        print(f"{'='*60}\n")
        
        # Step 1: Generate content with validation
        print("[1/6] Generating content with validation...")
        content = self._generate_and_validate_content(
            topic=topic,
            duration=duration,
            style=style
        )
        print(f"  Title: {content['title']}")
        print(f"  Segments: {len(content['segments'])}")
        
        # Save content for reference
        content_path = self.output_dir / "content.json"
        with open(content_path, 'w') as f:
            json.dump(content, f, indent=2)
        print(f"  Saved to: {content_path}")
        
        # Step 2: Generate audio with validation
        print("\n[2/6] Generating audio with validation...")
        audio_paths = await self._generate_and_validate_audio(content['segments'])
        print(f"  Generated {len(audio_paths)} valid audio files")
        
        # Step 3: Generate images with validation
        print("\n[3/6] Generating AI images with validation...")
        image_paths = await self._generate_and_validate_images(
            segments=content['segments'],
            images_enabled=images_enabled
        )
        
        # Step 4: Assemble video with sync engine for precise timing
        print("\n[4/6] Assembling video with frame-accurate sync...")
        
        # Calculate exact frame-aligned durations
        segment_durations = self.sync_engine.calculate_segment_durations(audio_paths)
        total_duration = sum(segment_durations)
        
        print(f"  Total duration: {total_duration:.2f}s ({int(total_duration * 30)} frames)")
        
        video_path = self.output_dir / f"{self._sanitize_filename(content['title'])}.mp4"
        self.video_asm.assemble_video_with_timing(
            segments=content['segments'],
            audio_paths=audio_paths,
            image_paths=image_paths,
            segment_durations=segment_durations,
            output_path=str(video_path)
        )
        print(f"  Video saved to: {video_path}")
        
        # Verify sync
        sync_check = self.sync_engine.verify_sync(str(video_path), total_duration)
        if sync_check['is_synced']:
            print(f"  Sync verified: {sync_check['difference_ms']:.1f}ms deviation")
        else:
            print(f"  Warning: Sync deviation {sync_check['difference_ms']:.1f}ms")
        
        # Step 5: Generate and add beat-synchronized background music
        if music_enabled and self.music_gen:
            print("\n[5/6] Generating beat-synced background music...")
            try:
                # Get exact video duration for precise sync
                from moviepy.editor import VideoFileClip
                temp_video = VideoFileClip(str(video_path))
                exact_duration = temp_video.duration
                temp_video.close()
                
                music_config = MusicConfig(
                    duration=30,  # Generate base loop
                    genre=music_genre,
                    mood=music_mood,
                    tempo="medium",
                    instrumental=True
                )
                
                # Generate music
                music_path = self.music_gen.generate_music(
                    config=music_config,
                    provider="local"
                )
                
                # Create beat-matched loop with sync engine
                beat_matched_path = str(self.temp_dir / "music_beat_matched.mp3")
                self.sync_engine.create_beat_matched_music(
                    music_path=music_path,
                    target_duration=exact_duration,
                    output_path=beat_matched_path,
                    bpm=120  # Standard BPM for sync
                )
                
                # Sync mix with audio ducking
                final_audio_path = str(self.temp_dir / "final_audio_mixed.mp3")
                self.sync_engine.sync_audio_levels(
                    voice_path=str(video_path),
                    music_path=beat_matched_path,
                    output_path=final_audio_path,
                    voice_db=0,
                    music_db=-20
                )
                
                # Apply to video
                final_video_path = self.output_dir / f"{self._sanitize_filename(content['title'])}_synced.mp4"
                self.video_asm.add_background_music(
                    video_path=str(video_path),
                    music_path=final_audio_path,
                    output_path=str(final_video_path),
                    music_volume=1.0
                )
                
                video_path = final_video_path
                print(f"  Beat-synced music added: {music_genre} / {music_mood}")
                
            except Exception as e:
                print(f"  Music generation skipped: {e}")
        else:
            print("\n[5/6] Skipping background music (disabled)")
        
        # Step 6: Create thumbnail
        print("\n[6/6] Creating thumbnail...")
        thumb_path = self.output_dir / f"{self._sanitize_filename(content['title'])}_thumb.jpg"
        self.video_asm.create_thumbnail(
            title=content['title'],
            output_path=str(thumb_path)
        )
        print(f"  Thumbnail saved to: {thumb_path}")
        
        result = {
            "topic": topic,
            "title": content['title'],
            "description": content['description'],
            "tags": content['tags'],
            "video_path": str(video_path),
            "thumbnail_path": str(thumb_path),
            "content": content,
            "uploaded": False,
            "video_id": None
        }
        
        # Optional: Upload to YouTube
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
                
                # Set thumbnail
                self.uploader.set_thumbnail(video_id, str(thumb_path))
        
        # Save result
        result_path = self.output_dir / "result.json"
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\n{'='*60}")
        print(f"PIPELINE COMPLETE!")
        print(f"Video: {video_path}")
        if result.get('video_url'):
            print(f"YouTube: {result['video_url']}")
        print(f"{'='*60}\n")
        
        return result
    
    def _sanitize_filename(self, filename: str) -> str:
        """Create safe filename from title."""
        import re
        safe = re.sub(r'[^\w\s-]', '', filename).strip().lower()
        safe = re.sub(r'[-\s]+', '-', safe)
        return safe[:50] or "video"
    
    def _generate_and_validate_content(self, topic: str, duration: int, style: str) -> Dict:
        """Generate content with validation and retry logic."""
        max_retries = self.retry_manager.max_retries
        
        for attempt in range(max_retries):
            try:
                content = self.content_gen.generate_script(
                    topic=topic,
                    duration_seconds=duration,
                    style=style
                )
                
                if self.validation_enabled:
                    validation = self.validator.validate_script(topic, content, duration)
                    
                    if validation['valid']:
                        print(f"  Validated (score: {validation['score']:.2f})")
                        return content
                    else:
                        print(f"  Validation failed: {validation['errors']}")
                        print(f"  Score: {validation['score']:.2f} - Retrying...")
                        
                        if attempt < max_retries - 1:
                            continue
                        else:
                            print("  Max retries reached, using best attempt")
                            return content
                else:
                    return content
                    
            except Exception as e:
                print(f"  Generation error: {e}")
                if attempt < max_retries - 1:
                    print("  Retrying...")
                else:
                    raise
        
        raise RuntimeError("Failed to generate valid content after max retries")
    
    async def _generate_and_validate_audio(self, segments: List[Dict]) -> List[str]:
        """Generate audio with validation and retry logic."""
        audio_paths = []
        
        for i, segment in enumerate(segments):
            seg_type = segment.get("type", f"segment_{i}")
            max_retries = self.retry_manager.max_retries
            
            for attempt in range(max_retries):
                try:
                    # Generate audio for this segment
                    text = segment.get("text", "")
                    audio_path = await self.media_gen.generate_speech(text)
                    
                    if self.validation_enabled and audio_path:
                        validation = self.validator.validate_audio(
                            audio_path=audio_path,
                            expected_text=text
                        )
                        
                        if validation['valid']:
                            print(f"  {seg_type}: Validated (score: {validation['score']:.2f})")
                            audio_paths.append(audio_path)
                            break
                        else:
                            print(f"  {seg_type}: Validation failed - {validation['errors']}")
                            if attempt < max_retries - 1:
                                print(f"  Retrying...")
                                continue
                            else:
                                print(f"  Max retries, using as-is")
                                audio_paths.append(audio_path)
                                break
                    else:
                        audio_paths.append(audio_path)
                        break
                        
                except Exception as e:
                    print(f"  {seg_type}: Generation error - {e}")
                    if attempt < max_retries - 1:
                        print("  Retrying...")
                    else:
                        raise
        
        return audio_paths
    
    async def _generate_and_validate_images(self, segments: List[Dict], 
                                            images_enabled: bool) -> List[Optional[str]]:
        """Generate images with validation and retry logic."""
        if not images_enabled or not self.image_gen:
            return [None] * len(segments)
        
        image_paths = []
        
        for i, segment in enumerate(segments):
            seg_type = segment.get("type", "content")
            
            # Skip intro/outro or segments without visual suggestions
            if seg_type != "content":
                image_paths.append(None)
                continue
            
            visual = segment.get("visual_suggestion", "")
            text = segment.get("text", "")
            
            max_retries = self.retry_manager.max_retries
            
            for attempt in range(max_retries):
                try:
                    # Generate image
                    img_path = self.image_gen.generate_image(
                        prompt=visual or text[:100],
                        output_path=str(self.temp_dir / f"validated_img_{i:03d}.png")
                    )
                    
                    if self.validation_enabled and img_path:
                        validation = self.validator.validate_image(
                            image_path=img_path,
                            scene_text=text,
                            visual_suggestion=visual
                        )
                        
                        if validation['valid']:
                            print(f"  Scene {i}: Validated (score: {validation['score']:.2f})")
                            image_paths.append(img_path)
                            break
                        else:
                            print(f"  Scene {i}: Validation failed - {validation['errors']}")
                            if attempt < max_retries - 1:
                                print("  Retrying with enhanced prompt...")
                                # Enhance prompt for retry
                                visual = f"high quality, detailed, {visual or text[:80]}"
                                continue
                            else:
                                print("  Max retries, using as-is")
                                image_paths.append(img_path)
                                break
                    else:
                        image_paths.append(img_path)
                        break
                        
                except Exception as e:
                    print(f"  Scene {i}: Generation error - {e}")
                    if attempt < max_retries - 1:
                        print("  Retrying...")
                    else:
                        image_paths.append(None)
                        break
        
        return image_paths


def main():
    parser = argparse.ArgumentParser(description="YouTube Content Creation Pipeline with Advanced Features")
    parser.add_argument("--topic", required=True, help="Video topic/subject")
    parser.add_argument("--duration", type=int, default=60, help="Target duration in seconds")
    parser.add_argument("--style", default="educational", help="Content style")
    parser.add_argument("--theme", default="modern", choices=["modern", "minimal", "vibrant", "corporate", "cinematic"],
                       help="Visual theme for video consistency")
    parser.add_argument("--provider", default=None, help="LLM provider (ollama, groq, gemini, or auto)")
    
    # Aspect ratio and video preset options
    parser.add_argument("--aspect-ratio", default="16:9", 
                       choices=["16:9", "9:16", "1:1", "4:3", "21:9"],
                       help="Video aspect ratio")
    parser.add_argument("--preset", default=None,
                       choices=["youtube_standard", "youtube_shorts", "instagram_post", 
                               "tiktok", "cinematic", "fast_export"],
                       help="Video preset configuration")
    parser.add_argument("--quality", default="high",
                       choices=["low", "medium", "high", "ultra"],
                       help="Export quality preset")
    
    # Music options
    parser.add_argument("--music", action="store_true", default=True, help="Add AI-generated background music")
    parser.add_argument("--no-music", dest="music", action="store_false", help="Disable background music")
    parser.add_argument("--music-genre", default="ambient", 
                       choices=["ambient", "electronic", "cinematic", "lofi", "piano"],
                       help="Music genre for background")
    parser.add_argument("--music-mood", default="calm",
                       choices=["calm", "upbeat", "dark", "epic"],
                       help="Music mood/atmosphere")
    
    # Image and visual options
    parser.add_argument("--images", action="store_true", default=True, help="Add AI-generated images per scene")
    parser.add_argument("--no-images", dest="images", action="store_false", help="Disable AI images")
    
    # Advanced effects
    parser.add_argument("--captions", action="store_true", help="Enable captions/subtitles")
    parser.add_argument("--ken-burns", action="store_true", help="Enable Ken Burns effect on images")
    parser.add_argument("--transition", default="fade",
                       choices=["fade", "slide", "zoom", "wipe", "none"],
                       help="Scene transition style")
    parser.add_argument("--color-grading", default=None,
                       choices=["warm", "cool", "vintage", "dramatic"],
                       help="Color grading style")
    parser.add_argument("--text-animation", default="fade",
                       choices=["fade", "slide_up", "bounce", "typewriter", "none"],
                       help="Text animation style")
    
    # Upload options
    parser.add_argument("--upload", action="store_true", help="Upload to YouTube")
    parser.add_argument("--privacy", default="private", 
                       choices=["private", "unlisted", "public"],
                       help="Upload privacy setting")
    
    args = parser.parse_args()
    
    # Build video config from CLI args or preset
    video_config = None
    if args.preset:
        from video_effects import get_preset
        video_config = get_preset(args.preset)
    
    # Initialize pipeline with all options
    pipeline = YouTubePipeline(
        provider_name=args.provider,
        theme=args.theme,
        music_enabled=args.music,
        images_enabled=args.images,
        aspect_ratio=args.aspect_ratio if not args.preset else None,
        video_preset=args.preset,
        video_config=video_config
    )
    
    # Run pipeline
    result = asyncio.run(pipeline.create_video(
        topic=args.topic,
        duration=args.duration,
        style=args.style,
        theme=args.theme,
        music_genre=args.music_genre,
        music_mood=args.music_mood,
        music_enabled=args.music,
        images_enabled=args.images,
        upload=args.upload,
        privacy=args.privacy
    ))
    
    # Print summary
    print("\n" + "="*60)
    print("VIDEO GENERATION COMPLETE")
    print("="*60)
    print(f"  Title: {result['title']}")
    print(f"  Tags: {', '.join(result['tags'])}")
    print(f"  Video: {result['video_path']}")
    if result['uploaded']:
        print(f"  YouTube: {result['video_url']}")
    print("="*60)


if __name__ == "__main__":
    main()
