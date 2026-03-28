"""Media generation module for TTS audio and image creation."""

import os
import asyncio
import re
from typing import Optional, List
from pathlib import Path

import edge_tts
import requests
from PIL import Image, ImageDraw, ImageFont


def _get_system_font():
    """Get a system font path that works across platforms."""
    import platform
    import os
    
    # Common font paths by platform
    font_paths = []
    
    if platform.system() == "Linux":
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
    elif platform.system() == "Darwin":  # macOS
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    elif platform.system() == "Windows":
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/Arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]
    
    # Find first available font
    for path in font_paths:
        if os.path.exists(path):
            return path
    
    return None  # Will fall back to default




class MediaGenerator:
    """Generates audio and visual media for videos."""
    
    def __init__(self, output_dir: str = "temp"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.audio_dir = self.output_dir / "audio"
        self.image_dir = self.output_dir / "images"
        self.audio_dir.mkdir(exist_ok=True)
        self.image_dir.mkdir(exist_ok=True)
    
    async def generate_speech(self, text: str, output_path: Optional[str] = None, 
                              voice: str = "en-US-AriaNeural") -> str:
        """Generate speech from text using Edge TTS (free)."""
        clean_text = self._clean_text_for_tts(text)
        
        if output_path is None:
            output_path = self.audio_dir / f"speech_{hash(text) % 100000:05d}.mp3"
        else:
            output_path = Path(output_path)
        
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(str(output_path))
        
        return str(output_path)
    
    async def generate_speech_segments(self, segments: List[dict], 
                                         voice: str = "en-US-AriaNeural") -> List[str]:
        """Generate speech for multiple segments."""
        audio_paths = []
        for i, segment in enumerate(segments):
            text = segment.get("text", "")
            if text:
                path = self.audio_dir / f"segment_{i:03d}.mp3"
                await self.generate_speech(text, str(path), voice)
                audio_paths.append(str(path))
        return audio_paths
    
    def _clean_text_for_tts(self, text: str) -> str:
        """Clean text for TTS - remove tags, normalize."""
        text = re.sub(r'\[PAUSE\]', '... ', text, flags=re.IGNORECASE)
        text = re.sub(r'\[.*?\]', '', text)
        text = text.replace('\n', ' ')
        return text.strip()
    
    def generate_text_image(self, text: str, output_path: Optional[str] = None,
                          width: int = 1920, height: int = 1080,
                          bg_color: str = "#1a1a2e", text_color: str = "#ffffff") -> str:
        """Generate an image with text overlay."""
        if output_path is None:
            output_path = self.image_dir / f"text_{hash(text) % 100000:05d}.png"
        else:
            output_path = Path(output_path)
        
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        
        font_path = _get_system_font()
        try:
            if font_path:
                font = ImageFont.truetype(font_path, 80)
            else:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] < width - 200:
                current_line.append(word)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        
        total_height = len(lines) * 100
        y_start = (height - total_height) // 2
        
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (width - bbox[2]) // 2
            y = y_start + i * 100
            draw.text((x, y), line, font=font, fill=text_color)
        
        img.save(output_path)
        return str(output_path)
    
    def generate_gradient_background(self, output_path: str, 
                                     width: int = 1920, height: int = 1080) -> str:
        """Generate a gradient background image."""
        img = Image.new('RGB', (width, height))
        
        for y in range(height):
            r = int(26 + (60 - 26) * y / height)
            g = int(26 + (20 - 26) * y / height)
            b = int(46 + (80 - 46) * y / height)
            for x in range(width):
                img.putpixel((x, y), (r, g, b))
        
        img.save(output_path)
        return output_path
    
    def download_stock_image(self, query: str, output_path: str) -> Optional[str]:
        """Download stock image - disabled as Unsplash API deprecated."""
        # Unsplash Source API is deprecated (2022), returns 404
        # Use Pollinations AI via image_generator.py instead
        return None


if __name__ == "__main__":
    import asyncio
    
    async def test():
        gen = MediaGenerator()
        
        # Test TTS
        audio_path = await gen.generate_speech("Hello! This is a test of the text to speech system.")
        print(f"Generated audio: {audio_path}")
        
        # Test image
        img_path = gen.generate_text_image("Welcome to the Future")
        print(f"Generated image: {img_path}")
    
    asyncio.run(test())
