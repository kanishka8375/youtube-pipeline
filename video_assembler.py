"""Video assembly module with consistent visual themes and advanced effects."""

import os
from typing import List, Optional, Tuple
from pathlib import Path
import numpy as np

from moviepy.editor import (
    AudioFileClip, ImageClip, concatenate_videoclips,
    CompositeVideoClip, TextClip, ColorClip
)
from moviepy.video.fx.all import fadein, fadeout

from video_themes import VideoTheme, get_theme, THEMES
from video_effects import VideoConfig, AspectRatio, VideoEffects, CaptionGenerator


class VideoAssembler:
    """Assembles audio and images into final video with theming and advanced effects."""
    
    def __init__(self, output_dir: str = "output", theme: str = "modern", 
                 video_config: Optional[VideoConfig] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Video configuration
        self.config = video_config or VideoConfig()
        self.effects = VideoEffects(self.config)
        self.size = self.config.aspect_ratio.value
        self.fps = self.config.fps
        
        # Theme
        self.theme = get_theme(theme)
        
        # Caption generator
        self.caption_gen = CaptionGenerator(self.config.caption_style) if self.config.enable_captions else None
    
    def set_theme(self, theme_name: str):
        """Change the visual theme."""
        self.theme = get_theme(theme_name)
    
    def assemble_video_with_timing(self, segments: List[dict], 
                                   audio_paths: List[str],
                                   image_paths: Optional[List[Optional[str]]] = None,
                                   segment_durations: Optional[List[float]] = None,
                                   output_path: Optional[str] = None,
                                   theme: Optional[str] = None) -> str:
        """
        Assemble video with precise timing control for frame-accurate sync.
        Uses pre-calculated segment durations to ensure perfect audio-visual alignment.
        """
        if theme:
            self.set_theme(theme)
        
        if output_path is None:
            output_path = self.output_dir / "final_video.mp4"
        else:
            output_path = Path(output_path)
        
        # Ensure image_paths matches segments length
        if image_paths is None:
            image_paths = [None] * len(segments)
        
        # Ensure segment_durations matches
        if segment_durations is None:
            segment_durations = [None] * len(segments)
        
        video_clips = []
        
        for i, (segment, audio_path, image_path, target_duration) in enumerate(
            zip(segments, audio_paths, image_paths, segment_durations)
        ):
            if not os.path.exists(audio_path):
                continue
            
            # Load audio
            audio = AudioFileClip(audio_path)
            
            # Use target duration if provided (from sync engine), otherwise use audio duration
            if target_duration is not None:
                # Trim or pad audio to exact target duration
                if audio.duration > target_duration:
                    audio = audio.subclip(0, target_duration)
                elif audio.duration < target_duration:
                    # Pad with silence
                    silence_duration = target_duration - audio.duration
                    from moviepy.editor import AudioClip
                    silence = AudioClip(lambda t: 0, duration=silence_duration)
                    from moviepy.editor import concatenate_audioclips
                    audio = concatenate_audioclips([audio, silence])
                duration = target_duration
            else:
                duration = audio.duration
            
            # Frame-align the duration
            frames = round(duration * self.fps)
            aligned_duration = frames / self.fps
            
            # Ensure audio matches aligned duration exactly
            if abs(audio.duration - aligned_duration) > 0.001:
                if audio.duration > aligned_duration:
                    audio = audio.subclip(0, aligned_duration)
                else:
                    # Add tiny bit of silence
                    padding = aligned_duration - audio.duration
                    from moviepy.editor import AudioClip
                    silence = AudioClip(lambda t: 0, duration=padding)
                    from moviepy.editor import concatenate_audioclips
                    audio = concatenate_audioclips([audio, silence])
            
            # Create visual with exact duration
            visual = self._create_visual(segment, aligned_duration, i, image_path)
            visual = visual.set_audio(audio)
            
            video_clips.append(visual)
        
        if not video_clips:
            raise ValueError("No video clips generated")
        
        # Concatenate with frame-accurate timing
        final = concatenate_videoclips(video_clips, method="compose")
        
        # Ensure final duration is frame-aligned
        total_frames = round(final.duration * self.fps)
        exact_duration = total_frames / self.fps
        
        if abs(final.duration - exact_duration) > 0.001:
            final = final.subclip(0, exact_duration)
        
        # Apply effects
        final = self.effects.add_watermark(final)
        final = self.effects.apply_color_grading(final)
        
        # Get quality settings
        ffmpeg_params = self.effects.get_ffmpeg_params()
        
        # Write with quality preset settings
        final.write_videofile(
            str(output_path),
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=str(self.output_dir / "temp_audio.m4a"),
            remove_temp=True,
            audio_fps=44100,
            preset=ffmpeg_params['preset'],
            bitrate=ffmpeg_params['bitrate'],
            threads=4,
            logger=None  # Suppress verbose output
        )
        
        return str(output_path)
    
    def assemble_video(self, segments: List[dict], 
                       audio_paths: List[str],
                       image_paths: Optional[List[Optional[str]]] = None,
                       output_path: Optional[str] = None,
                       theme: Optional[str] = None) -> str:
        """Backwards-compatible wrapper for assemble_video_with_timing."""
        return self.assemble_video_with_timing(
            segments=segments,
            audio_paths=audio_paths,
            image_paths=image_paths,
            segment_durations=None,  # Will calculate from audio
            output_path=output_path,
            theme=theme
        )
    
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
        """Get background color for scene type ensuring consistency."""
        if seg_type == "intro" and self.theme.intro_bg:
            return self.theme.intro_bg
        elif seg_type == "outro" and self.theme.outro_bg:
            return self.theme.outro_bg
        elif seg_type == "content" and self.theme.content_bg:
            return self.theme.content_bg
        return self.theme.bg_color
    
    def _create_text_clip(self, text: str, duration: float, 
                          is_title: bool = False) -> TextClip:
        """Create text with consistent theme styling."""
        fontsize = self.theme.title_font_size if is_title else self.theme.body_font_size
        max_width = self.theme.max_text_width if not is_title else self.size[0] - 40
        
        stroke_color = None
        stroke_width = 0
        
        # Add stroke for better visibility on certain themes
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
        """Create image clip with Ken Burns effect and proper aspect ratio sizing."""
        try:
            img_clip = ImageClip(image_path)
            
            # Calculate dimensions based on aspect ratio
            target_width = self.size[0] * 0.75
            target_height = self.size[1] * 0.55
            
            # Resize maintaining aspect ratio
            img_clip = img_clip.resize(
                width=target_width,
                height=target_height
            )
            
            # Apply Ken Burns effect if enabled
            if self.config.enable_ken_burns:
                img_clip = self.effects.apply_ken_burns(img_clip, duration)
            
            # Position in center-top area
            img_clip = img_clip.set_position(("center", "top")).margin(top=60)
            img_clip = img_clip.set_duration(duration)
            
            # Add fade
            img_clip = fadein(img_clip, self.theme.fade_duration)
            img_clip = fadeout(img_clip, self.theme.fade_duration)
            
            return img_clip
            
        except Exception as e:
            print(f"  Failed to create image clip: {e}")
            return None
    
    def _create_visual(self, segment: dict, duration: float, index: int, image_path: Optional[str] = None) -> ImageClip:
        """Create visual component with effects, captions, and animations."""
        seg_type = segment.get("type", "content")
        text = segment.get("text", "")[:200]
        
        # Get consistent background
        bg_color = self._get_scene_background(seg_type)
        bg_gradient_end = self.theme.bg_gradient_end if self.theme.use_gradient else None
        
        # Create background
        bg = self._create_gradient_background(duration, bg_color, bg_gradient_end)
        clips = [bg]
        
        # Add AI-generated image if available
        if image_path and os.path.exists(image_path) and seg_type == "content":
            img_clip = self._create_image_clip(image_path, duration)
            if img_clip:
                clips.append(img_clip)
        
        # Add accent border if theme has it
        if self.theme.add_border and self.theme.border_width > 0:
            border = self._create_border(duration)
            clips.append(border)
        
        if seg_type == "intro":
            title = segment.get("title", "")
            display_text = title if title else text
            
            # Title with animation
            txt = self._create_text_clip(display_text, duration, is_title=True)
            txt = self.effects.apply_text_animation(txt, duration)
            txt = txt.set_position("center")
            clips.append(txt)
            
            # Add branding
            brand = self._create_brand_element(duration)
            if brand:
                clips.append(brand)
                
        elif seg_type == "outro":
            outro_text = "Thanks for watching!\nSubscribe for more"
            txt = self._create_text_clip(outro_text, duration, is_title=False)
            txt = self.effects.apply_text_animation(txt, duration)
            txt = txt.set_position("center")
            clips.append(txt)
            
        else:
            # Content scene with captions if enabled
            if text:
                txt = self._create_text_clip(text, duration, is_title=False)
                txt = self.effects.apply_text_animation(txt, duration)
                
                # Position text
                if image_path and os.path.exists(image_path):
                    txt = txt.set_position(("center", "bottom")).margin(bottom=60)
                else:
                    txt = txt.set_position("center")
                clips.append(txt)
                
                # Add captions overlay if enabled
                if self.caption_gen and self.config.enable_captions:
                    caption = self.caption_gen.create_caption_clip(text[:100], duration, self.size)
                    clips.append(caption)
        
        # Compose all elements
        if len(clips) > 1:
            clip = CompositeVideoClip(clips)
        else:
            clip = clips[0]
        
        # Apply consistent fade effects
        clip = fadein(clip, self.theme.fade_duration)
        clip = fadeout(clip, self.theme.fade_duration)
        
        return clip
    
    def _create_border(self, duration: float) -> ColorClip:
        """Create accent border overlay."""
        from moviepy.editor import ImageClip
        import numpy as np
        
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
    
    def _create_brand_element(self, duration: float) -> Optional[TextClip]:
        """Create subtle branding element (e.g., channel name placeholder)."""
        # Can be customized to show logo/watermark
        return None
    
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex to RGB."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def create_thumbnail(self, title: str, output_path: Optional[str] = None) -> str:
        """Create thumbnail matching video theme and aspect ratio."""
        if output_path is None:
            output_path = self.output_dir / "thumbnail.jpg"
        else:
            output_path = Path(output_path)
        
        # Thumbnail size based on aspect ratio
        if self.size[1] > self.size[0]:  # Portrait (Shorts)
            thumb_size = (720, 1280)
            fontsize = 60
        elif self.size[0] == self.size[1]:  # Square
            thumb_size = (1080, 1080)
            fontsize = 70
        else:  # Landscape (standard)
            thumb_size = (1280, 720)
            fontsize = 75
        
        thumb_bg = self._hex_to_rgb(self.theme.accent_color)
        bg = ColorClip(size=thumb_size, color=thumb_bg, duration=1)
        
        # Title with responsive sizing
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
    
    def add_background_music(self, video_path: str, music_path: str,
                            output_path: str, music_volume: float = 0.3) -> str:
        """Add background music to video."""
        from moviepy.editor import VideoFileClip, CompositeAudioClip
        
        video = VideoFileClip(video_path)
        music = AudioFileClip(music_path).volumex(music_volume)
        
        if music.duration > video.duration:
            music = music.subclip(0, video.duration)
        else:
            music = music.loop(duration=video.duration)
        
        composite = CompositeAudioClip([video.audio, music])
        final = video.set_audio(composite)
        
        final.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            audio_codec="aac"
        )
        
        video.close()
        music.close()
        
        return output_path


if __name__ == "__main__":
    assembler = VideoAssembler(theme="modern")
    
    # Test with different themes
    for theme_name in THEMES.keys():
        assembler.set_theme(theme_name)
        thumb = assembler.create_thumbnail(f"Video with {theme_name} theme")
        print(f"Created thumbnail for {theme_name}: {thumb}")
