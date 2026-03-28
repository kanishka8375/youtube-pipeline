"""Simplified video assembly with just fade transitions."""

import os
from typing import List, Optional, Tuple
from pathlib import Path
import numpy as np

from moviepy.editor import (
    AudioFileClip, ImageClip, concatenate_videoclips,
    CompositeVideoClip, TextClip, ColorClip
)
from moviepy.video.fx.all import fadein, fadeout

from video_themes import get_theme


class VideoAssembler:
    """Assembles audio and images into video with simple fade transitions."""
    
    def __init__(self, output_dir: str = "output", theme: str = "modern"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.size = (1920, 1080)
        self.fps = 30
        self.theme = get_theme(theme)
    
    def set_theme(self, theme_name: str):
        """Change the visual theme."""
        self.theme = get_theme(theme_name)
    
    def assemble_video(self, segments: List[dict], 
                       audio_paths: List[str],
                       image_paths: Optional[List[Optional[str]]] = None,
                       output_path: Optional[str] = None) -> str:
        """Assemble video with fade transitions."""
        
        if output_path is None:
            output_path = self.output_dir / "final_video.mp4"
        else:
            output_path = Path(output_path)
        
        if image_paths is None:
            image_paths = [None] * len(segments)
        
        video_clips = []
        
        for i, (segment, audio_path, image_path) in enumerate(
            zip(segments, audio_paths, image_paths)
        ):
            if not os.path.exists(audio_path):
                continue
            
            # Load audio
            audio = AudioFileClip(audio_path)
            duration = audio.duration
            
            # Create visual
            visual = self._create_visual(segment, duration, image_path)
            visual = visual.set_audio(audio)
            
            # Add fade transitions
            visual = fadein(visual, self.theme.fade_duration)
            visual = fadeout(visual, self.theme.fade_duration)
            
            video_clips.append(visual)
        
        if not video_clips:
            raise ValueError("No video clips generated")
        
        # Concatenate all clips
        final = concatenate_videoclips(video_clips, method="compose")
        
        # Write video
        final.write_videofile(
            str(output_path),
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=str(self.output_dir / "temp_audio.m4a"),
            remove_temp=True,
            preset='medium',
            threads=4,
            logger=None
        )
        
        return str(output_path)
    
    def _create_gradient_background(self, duration: float, 
                                     start_color: Tuple[int, int, int],
                                     end_color: Optional[Tuple[int, int, int]] = None) -> ColorClip:
        """Create gradient background if theme uses gradients."""
        if end_color is None or not self.theme.use_gradient:
            return ColorClip(size=self.size, color=start_color, duration=duration)
        
        # Create gradient image
        gradient = np.zeros((self.size[1], self.size[0], 3), dtype=np.uint8)
        
        for y in range(self.size[1]):
            ratio = y / self.size[1]
            r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
            g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
            b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
            gradient[y, :] = [r, g, b]
        
        return ImageClip(gradient, duration=duration)
    
    def _get_scene_background(self, seg_type: str) -> Tuple[int, int, int]:
        """Get background color for scene type."""
        if seg_type == "intro" and self.theme.intro_bg:
            return self.theme.intro_bg
        elif seg_type == "outro" and self.theme.outro_bg:
            return self.theme.outro_bg
        elif seg_type == "content" and self.theme.content_bg:
            return self.theme.content_bg
        return self.theme.bg_color
    
    def _create_text_clip(self, text: str, duration: float, 
                          is_title: bool = False) -> TextClip:
        """Create text with theme styling."""
        fontsize = self.theme.title_font_size if is_title else self.theme.body_font_size
        max_width = self.theme.max_text_width if not is_title else self.size[0] - 40
        
        stroke_color = None
        stroke_width = 0
        
        if self.theme.name in ["vibrant", "cinematic"]:
            stroke_color = "black"
            stroke_width = 2
        
        txt = TextClip(
            text,
            fontsize=fontsize,
            color=self.theme.text_color,
            font=self.theme.font_family,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            size=(max_width, self.size[1]),
            method="caption",
            align="center"
        ).set_duration(duration)
        
        return txt
    
    def _create_image_clip(self, image_path: str, duration: float) -> Optional[ImageClip]:
        """Create image clip with proper sizing."""
        try:
            img_clip = ImageClip(image_path)
            
            # Calculate dimensions
            target_width = self.size[0] * 0.75
            target_height = self.size[1] * 0.55
            
            # Resize maintaining aspect ratio
            img_clip = img_clip.resize(
                width=target_width,
                height=target_height
            )
            
            # Position in center-top area
            img_clip = img_clip.set_position(("center", "top")).margin(top=60)
            img_clip = img_clip.set_duration(duration)
            
            # Add fade
            img_clip = fadein(img_clip, self.theme.fade_duration)
            img_clip = fadeout(img_clip, self.theme.fade_duration)
            
            return img_clip
            
        except Exception as e:
            print(f"  Image clip error: {e}")
            return None
    
    def _create_visual(self, segment: dict, duration: float, image_path: Optional[str] = None):
        """Create visual component with fade transitions only."""
        seg_type = segment.get("type", "content")
        text = segment.get("text", "")[:200]
        
        # Get background
        bg_color = self._get_scene_background(seg_type)
        bg_gradient_end = self.theme.bg_gradient_end if self.theme.use_gradient else None
        
        # Create background
        bg = self._create_gradient_background(duration, bg_color, bg_gradient_end)
        clips = [bg]
        
        # Add image if available
        if image_path and os.path.exists(image_path) and seg_type == "content":
            img_clip = self._create_image_clip(image_path, duration)
            if img_clip:
                clips.append(img_clip)
        
        # Add border if theme has it
        if self.theme.add_border and self.theme.border_width > 0:
            border = self._create_border(duration)
            clips.append(border)
        
        if seg_type == "intro":
            title = segment.get("title", "")
            display_text = title if title else text
            
            txt = self._create_text_clip(display_text, duration, is_title=True)
            txt = txt.set_position("center")
            clips.append(txt)
                
        elif seg_type == "outro":
            outro_text = "Thanks for watching!\nSubscribe for more"
            txt = self._create_text_clip(outro_text, duration, is_title=False)
            txt = txt.set_position("center")
            clips.append(txt)
            
        else:
            # Content scene
            if text:
                txt = self._create_text_clip(text, duration, is_title=False)
                if image_path and os.path.exists(image_path):
                    txt = txt.set_position(("center", "bottom")).margin(bottom=60)
                else:
                    txt = txt.set_position("center")
                clips.append(txt)
        
        # Compose all elements
        if len(clips) > 1:
            clip = CompositeVideoClip(clips)
        else:
            clip = clips[0]
        
        return clip
    
    def _create_border(self, duration: float):
        """Create accent border overlay."""
        from moviepy.editor import ImageClip
        
        border_width = self.theme.border_width
        border_color = self._hex_to_rgb(self.theme.border_color)
        
        # Create transparent image with border
        img = np.zeros((self.size[1], self.size[0], 4), dtype=np.uint8)
        
        # Top and bottom borders
        img[:border_width, :, :3] = border_color
        img[:border_width, :, 3] = 255
        img[-border_width:, :, :3] = border_color
        img[-border_width:, :, 3] = 255
        
        # Left and right borders
        img[:, :border_width, :3] = border_color
        img[:, :border_width, 3] = 255
        img[:, -border_width:, :3] = border_color
        img[:, -border_width:, 3] = 255
        
        return ImageClip(img, duration=duration, ismask=False)
    
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex to RGB."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def create_thumbnail(self, title: str, output_path: Optional[str] = None) -> str:
        """Create thumbnail matching theme."""
        if output_path is None:
            output_path = self.output_dir / "thumbnail.jpg"
        else:
            output_path = Path(output_path)
        
        thumb_size = (1280, 720)
        fontsize = 75
        
        thumb_bg = self._hex_to_rgb(self.theme.accent_color)
        bg = ColorClip(size=thumb_size, color=thumb_bg, duration=1)
        
        txt = TextClip(
            title[:60],
            fontsize=fontsize,
            color=self.theme.text_color,
            font=self.theme.font_family,
            stroke_color="black",
            stroke_width=3,
            size=(thumb_size[0] - 80, thumb_size[1] - 100),
            method="caption",
            align="center"
        ).set_duration(1).set_position("center")
        
        thumb = CompositeVideoClip([bg, txt])
        thumb.save_frame(str(output_path))
        
        return str(output_path)
