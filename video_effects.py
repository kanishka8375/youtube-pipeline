"""Advanced video effects and aspect ratio support."""

from typing import Tuple, Optional, Literal, Dict, List
from dataclasses import dataclass
from enum import Enum
import numpy as np
from moviepy.editor import (
    VideoClip, ImageClip, TextClip, ColorClip, CompositeVideoClip,
    concatenate_videoclips, transfx
)
from moviepy.video.fx.all import (
    fadein, fadeout, resize, rotate, margin, scroll
)


class AspectRatio(Enum):
    """Supported aspect ratios."""
    LANDSCAPE_16_9 = (1920, 1080)  # Standard YouTube
    PORTRAIT_9_16 = (1080, 1920)   # YouTube Shorts / TikTok
    SQUARE_1_1 = (1080, 1080)      # Instagram
    CLASSIC_4_3 = (1440, 1080)     # Classic video
    CINEMATIC_21_9 = (2560, 1080)  # Ultra-wide
    SHORTS_9_16 = (1080, 1920)     # YouTube Shorts


@dataclass
class VideoConfig:
    """Configuration for video generation."""
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE_16_9
    fps: int = 30
    quality_preset: Literal["low", "medium", "high", "ultra"] = "high"
    
    # Effects
    enable_transitions: bool = True
    transition_type: Literal["fade", "slide", "wipe", "zoom", "none"] = "fade"
    transition_duration: float = 0.5
    
    # Animations
    enable_text_animations: bool = True
    text_animation: Literal["fade", "slide_up", "typewriter", "bounce", "none"] = "fade"
    
    # Image effects
    enable_ken_burns: bool = False  # Slow zoom/pan on images
    ken_burns_intensity: float = 0.1  # 0.0 to 1.0
    
    # Branding
    watermark_path: Optional[str] = None
    watermark_position: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "bottom_right"
    watermark_opacity: float = 0.7
    
    # Captions
    enable_captions: bool = False
    caption_style: Literal["classic", "modern", "minimal", "karaoke"] = "modern"
    caption_language: str = "en"
    
    # Advanced
    enable_motion_blur: bool = False
    color_grading: Optional[str] = None  # "warm", "cool", "vintage", "dramatic"


class VideoEffects:
    """Advanced video effects and transitions."""
    
    # Quality presets
    QUALITY_SETTINGS = {
        "low": {"bitrate": "2000k", "preset": "ultrafast", "crf": "28"},
        "medium": {"bitrate": "4000k", "preset": "fast", "crf": "23"},
        "high": {"bitrate": "8000k", "preset": "medium", "crf": "18"},
        "ultra": {"bitrate": "16000k", "preset": "slow", "crf": "15"}
    }
    
    def __init__(self, config: VideoConfig):
        self.config = config
        self.size = config.aspect_ratio.value
    
    def apply_transition(self, clip1: VideoClip, clip2: VideoClip, 
                         duration: float) -> List[VideoClip]:
        """Apply transition between two clips."""
        if not self.config.enable_transitions or self.config.transition_type == "none":
            return [clip1, clip2]
        
        t_type = self.config.transition_type
        t_duration = min(self.config.transition_duration, duration / 3)
        
        if t_type == "fade":
            # Crossfade
            clip1 = fadeout(clip1, t_duration)
            clip2 = fadein(clip2, t_duration)
            return [clip1, clip2]
        
        elif t_type == "slide":
            # Slide transition
            from moviepy.video.fx.all import slide_in
            clip2 = slide_in(clip2, duration=t_duration, side="left")
            return [clip1, clip2]
        
        elif t_type == "wipe":
            # Wipe effect using mask
            return [clip1, clip2]  # Simplified
        
        elif t_type == "zoom":
            # Zoom transition
            from moviepy.video.fx.all import resize
            clip1_end = resize(clip1, lambda t: 1 + 0.1 * (t / clip1.duration))
            return [clip1_end, clip2]
        
        return [clip1, clip2]
    
    def apply_ken_burns(self, clip: ImageClip, duration: float) -> VideoClip:
        """Apply Ken Burns effect (slow zoom and pan) to image."""
        if not self.config.enable_ken_burns:
            return clip
        
        intensity = self.config.ken_burns_intensity
        
        # Random direction for pan
        import random
        pan_x = random.choice([-1, 1]) * intensity * 0.1
        pan_y = random.choice([-1, 1]) * intensity * 0.05
        zoom_factor = 1.0 + (intensity * 0.2)
        
        def ken_burns_frame(get_frame, t):
            frame = get_frame(t)
            progress = t / duration
            
            # Calculate zoom and position
            current_zoom = 1.0 + (zoom_factor - 1.0) * progress
            offset_x = int(pan_x * progress * frame.shape[1])
            offset_y = int(pan_y * progress * frame.shape[0])
            
            # Resize
            from scipy.ndimage import zoom as scipy_zoom
            zoomed = scipy_zoom(frame, (current_zoom, current_zoom, 1), order=1)
            
            # Crop to original size
            h, w = frame.shape[:2]
            start_y = max(0, (zoomed.shape[0] - h) // 2 + offset_y)
            start_x = max(0, (zoomed.shape[1] - w) // 2 + offset_x)
            
            cropped = zoomed[start_y:start_y+h, start_x:start_x+w]
            return cropped[:h, :w]  # Ensure exact size
        
        return clip.fl(ken_burns_frame)
    
    def apply_text_animation(self, text_clip: TextClip, duration: float) -> VideoClip:
        """Apply animation to text."""
        if not self.config.enable_text_animations:
            return text_clip
        
        anim = self.config.text_animation
        
        if anim == "fade":
            return fadein(fadeout(text_clip, 0.3), 0.3)
        
        elif anim == "slide_up":
            from moviepy.video.fx.all import slide_in
            return slide_in(text_clip, duration=0.5, side="bottom")
        
        elif anim == "typewriter":
            # Simulate typewriter effect
            text = text_clip.txt
            char_duration = duration / len(text) if text else duration
            
            def typewriter_frame(get_frame, t):
                chars_to_show = int(t / char_duration)
                # This is simplified - actual implementation would need TextClip recreation
                return get_frame(t)
            
            return text_clip.fl(typewriter_frame)
        
        elif anim == "bounce":
            # Bounce in effect
            def bounce_pos(t):
                progress = min(t / 0.5, 1.0)
                # Simple bounce easing
                bounce = 1 - (1 - progress) ** 2
                return ("center", 50 + (1 - bounce) * 100)
            
            return text_clip.set_position(bounce_pos)
        
        return text_clip
    
    def add_watermark(self, clip: VideoClip) -> VideoClip:
        """Add watermark/logo overlay."""
        if not self.config.watermark_path or not self.config.watermark_path.exists():
            return clip
        
        try:
            from moviepy.editor import ImageClip
            watermark = ImageClip(self.config.watermark_path)
            
            # Resize watermark (max 15% of video width)
            max_width = self.size[0] * 0.15
            if watermark.w > max_width:
                watermark = watermark.resize(width=max_width)
            
            # Set position
            positions = {
                "top_left": (10, 10),
                "top_right": (self.size[0] - watermark.w - 10, 10),
                "bottom_left": (10, self.size[1] - watermark.h - 10),
                "bottom_right": (self.size[0] - watermark.w - 10, self.size[1] - watermark.h - 10)
            }
            
            pos = positions.get(self.config.watermark_position, positions["bottom_right"])
            watermark = watermark.set_position(pos).set_duration(clip.duration)
            
            # Apply opacity
            if self.config.watermark_opacity < 1.0:
                watermark = watermark.set_opacity(self.config.watermark_opacity)
            
            return CompositeVideoClip([clip, watermark])
        except Exception as e:
            print(f"Watermark error: {e}")
            return clip
    
    def apply_color_grading(self, clip: VideoClip) -> VideoClip:
        """Apply color grading effect."""
        if not self.config.color_grading:
            return clip
        
        grading = self.config.color_grading
        
        def color_grade_frame(get_frame, t):
            frame = get_frame(t).astype(float)
            
            if grading == "warm":
                # Increase red/yellow
                frame[:, :, 0] *= 1.1  # Red
                frame[:, :, 1] *= 1.05  # Green
                frame[:, :, 2] *= 0.95  # Blue
            
            elif grading == "cool":
                # Increase blue
                frame[:, :, 0] *= 0.95
                frame[:, :, 1] *= 1.0
                frame[:, :, 2] *= 1.1
            
            elif grading == "vintage":
                # Sepia-like effect
                r, g, b = frame[:, :, 0], frame[:, :, 1], frame[:, :, 2]
                frame[:, :, 0] = r * 0.9 + g * 0.3 + b * 0.1
                frame[:, :, 1] = r * 0.2 + g * 0.8 + b * 0.1
                frame[:, :, 2] = r * 0.1 + g * 0.2 + b * 0.7
            
            elif grading == "dramatic":
                # Increase contrast
                frame = (frame - 128) * 1.2 + 128
            
            return np.clip(frame, 0, 255).astype(np.uint8)
        
        return clip.fl(color_grade_frame)
    
    def get_ffmpeg_params(self) -> Dict[str, str]:
        """Get FFmpeg encoding parameters based on quality preset."""
        settings = self.QUALITY_SETTINGS.get(self.config.quality_preset, self.QUALITY_SETTINGS["high"])
        return settings


class CaptionGenerator:
    """Generate captions/subtitles for videos."""
    
    STYLES = {
        "classic": {
            "font": "Arial-Bold",
            "color": "white",
            "stroke_color": "black",
            "stroke_width": 2,
            "bg_color": None,
            "fontsize": 50
        },
        "modern": {
            "font": "Montserrat-Bold",
            "color": "white",
            "stroke_color": None,
            "stroke_width": 0,
            "bg_color": (0, 0, 0, 180),  # Semi-transparent black
            "fontsize": 48
        },
        "minimal": {
            "font": "Helvetica",
            "color": "white",
            "stroke_color": None,
            "stroke_width": 0,
            "bg_color": None,
            "fontsize": 40
        },
        "karaoke": {
            "font": "Arial-Bold",
            "color": "yellow",
            "stroke_color": "black",
            "stroke_width": 3,
            "bg_color": None,
            "fontsize": 52
        }
    }
    
    def __init__(self, style: str = "modern"):
        self.style = self.STYLES.get(style, self.STYLES["modern"])
    
    def create_caption_clip(self, text: str, duration: float, video_size: Tuple[int, int]) -> TextClip:
        """Create a caption text clip with styling."""
        style = self.style
        
        # Create background if needed
        clips = []
        
        txt_clip = TextClip(
            text,
            fontsize=style["fontsize"],
            color=style["color"],
            font=style["font"],
            stroke_color=style["stroke_color"],
            stroke_width=style["stroke_width"],
            method="caption",
            size=(video_size[0] - 100, None),
            align="center"
        ).set_duration(duration)
        
        # Add background box if specified
        if style["bg_color"]:
            from moviepy.editor import ColorClip
            bg = ColorClip(
                size=(txt_clip.w + 40, txt_clip.h + 20),
                color=style["bg_color"][:3]
            ).set_duration(duration).set_opacity(style["bg_color"][3] / 255 if len(style["bg_color"]) > 3 else 1.0)
            
            # Center text on background
            txt_clip = txt_clip.set_position("center")
            bg = bg.set_position(("center", video_size[1] - txt_clip.h - 100))
            
            return CompositeVideoClip([bg, txt_clip.set_position(("center", video_size[1] - txt_clip.h - 100))])
        
        # Position at bottom
        txt_clip = txt_clip.set_position(("center", video_size[1] - txt_clip.h - 80))
        
        return txt_clip


class BatchProcessor:
    """Process multiple videos in batch."""
    
    def __init__(self, pipeline, config: VideoConfig):
        self.pipeline = pipeline
        self.config = config
        self.jobs: List[Dict] = []
    
    def add_job(self, topic: str, **kwargs):
        """Add a video generation job."""
        self.jobs.append({
            "topic": topic,
            "kwargs": kwargs,
            "status": "pending",
            "result": None
        })
    
    async def process_all(self, max_concurrent: int = 2):
        """Process all jobs with concurrency limit."""
        import asyncio
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_job(job):
            async with semaphore:
                job["status"] = "running"
                try:
                    result = await self.pipeline.create_video(
                        topic=job["topic"],
                        **job["kwargs"]
                    )
                    job["status"] = "complete"
                    job["result"] = result
                except Exception as e:
                    job["status"] = "error"
                    job["error"] = str(e)
        
        await asyncio.gather(*[process_job(job) for job in self.jobs])
        return self.jobs


# Preset configurations for common use cases
VIDEO_PRESETS = {
    "youtube_standard": VideoConfig(
        aspect_ratio=AspectRatio.LANDSCAPE_16_9,
        quality_preset="high",
        enable_transitions=True,
        enable_text_animations=True
    ),
    "youtube_shorts": VideoConfig(
        aspect_ratio=AspectRatio.SHORTS_9_16,
        quality_preset="high",
        enable_transitions=True,
        transition_type="slide",
        enable_text_animations=True,
        text_animation="bounce"
    ),
    "instagram_post": VideoConfig(
        aspect_ratio=AspectRatio.SQUARE_1_1,
        quality_preset="high",
        enable_transitions=True,
        enable_captions=True,
        caption_style="modern"
    ),
    "tiktok": VideoConfig(
        aspect_ratio=AspectRatio.PORTRAIT_9_16,
        quality_preset="high",
        enable_transitions=True,
        transition_type="zoom",
        enable_text_animations=True,
        enable_captions=True,
        caption_style="modern"
    ),
    "cinematic": VideoConfig(
        aspect_ratio=AspectRatio.CINEMATIC_21_9,
        quality_preset="ultra",
        enable_transitions=True,
        transition_type="fade",
        enable_ken_burns=True,
        ken_burns_intensity=0.2,
        color_grading="dramatic"
    ),
    "fast_export": VideoConfig(
        aspect_ratio=AspectRatio.LANDSCAPE_16_9,
        quality_preset="low",
        enable_transitions=False,
        enable_text_animations=False
    )
}


def get_preset(name: str) -> VideoConfig:
    """Get a preset configuration by name."""
    return VIDEO_PRESETS.get(name, VIDEO_PRESETS["youtube_standard"])


if __name__ == "__main__":
    # Test presets
    for name in VIDEO_PRESETS.keys():
        config = get_preset(name)
        print(f"{name}: {config.aspect_ratio.name}, {config.quality_preset} quality")
