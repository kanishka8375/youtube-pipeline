"""Video theme system for consistent visual branding across all scenes."""

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class VideoTheme:
    """Visual theme configuration for consistent branding."""
    name: str
    
    # Colors
    bg_color: Tuple[int, int, int]
    bg_gradient_end: Optional[Tuple[int, int, int]] = None
    text_color: str = "#ffffff"
    accent_color: str = "#667eea"
    
    # Typography
    title_font_size: int = 80
    body_font_size: int = 50
    font_family: str = "DejaVu-Sans-Bold"
    
    # Layout
    text_padding: int = 100
    max_text_width: int = 1720  # 1920 - 2*padding
    
    # Effects
    fade_duration: float = 0.5
    use_gradient: bool = False
    add_border: bool = False
    border_color: str = "#667eea"
    border_width: int = 0
    
    # Scene-specific settings
    intro_bg: Optional[Tuple[int, int, int]] = None
    outro_bg: Optional[Tuple[int, int, int]] = None
    content_bg: Optional[Tuple[int, int, int]] = None


# Pre-defined themes for consistency
THEMES = {
    "modern": VideoTheme(
        name="Modern Dark",
        bg_color=(26, 26, 46),
        bg_gradient_end=(22, 33, 62),
        text_color="#ffffff",
        accent_color="#667eea",
        title_font_size=85,
        body_font_size=52,
        use_gradient=True,
        intro_bg=(26, 26, 46),
        outro_bg=(46, 26, 46),
        content_bg=(26, 40, 60)
    ),
    
    "minimal": VideoTheme(
        name="Minimal",
        bg_color=(245, 245, 245),
        text_color="#1a1a2e",
        accent_color="#333333",
        title_font_size=75,
        body_font_size=48,
        font_family="DejaVu-Sans",
        intro_bg=(240, 240, 240),
        outro_bg=(230, 230, 230),
        content_bg=(250, 250, 250)
    ),
    
    "vibrant": VideoTheme(
        name="Vibrant",
        bg_color=(102, 126, 234),
        bg_gradient_end=(118, 75, 162),
        text_color="#ffffff",
        accent_color="#ffd700",
        title_font_size=90,
        body_font_size=55,
        use_gradient=True,
        intro_bg=(102, 126, 234),
        outro_bg=(118, 75, 162),
        content_bg=(86, 100, 200)
    ),
    
    "corporate": VideoTheme(
        name="Corporate",
        bg_color=(255, 255, 255),
        text_color="#1a365d",
        accent_color="#2b6cb0",
        title_font_size=70,
        body_font_size=45,
        font_family="DejaVu-Sans-Bold",
        add_border=True,
        border_color="#2b6cb0",
        border_width=8,
        intro_bg=(255, 255, 255),
        outro_bg=(240, 248, 255),
        content_bg=(255, 255, 255)
    ),
    
    "cinematic": VideoTheme(
        name="Cinematic",
        bg_color=(15, 15, 15),
        bg_gradient_end=(40, 40, 40),
        text_color="#e0e0e0",
        accent_color="#c9a227",
        title_font_size=95,
        body_font_size=50,
        use_gradient=True,
        fade_duration=1.0,
        intro_bg=(10, 10, 10),
        outro_bg=(20, 20, 20),
        content_bg=(25, 25, 25)
    ),
    
    # Anime & Manga styles
    "anime": VideoTheme(
        name="Anime",
        bg_color=(255, 182, 193),
        bg_gradient_end=(147, 112, 219),
        text_color="#ffffff",
        accent_color="#ff69b4",
        title_font_size=85,
        body_font_size=50,
        use_gradient=True,
        intro_bg=(255, 105, 180),
        outro_bg=(147, 112, 219),
        content_bg=(230, 180, 200)
    ),
    
    "manga": VideoTheme(
        name="Manga",
        bg_color=(255, 255, 255),
        bg_gradient_end=(240, 240, 240),
        text_color="#000000",
        accent_color="#ff0000",
        title_font_size=90,
        body_font_size=55,
        font_family="DejaVu-Sans-Bold",
        add_border=True,
        border_color="#000000",
        border_width=4,
        intro_bg=(255, 255, 255),
        outro_bg=(240, 240, 240),
        content_bg=(250, 250, 250)
    ),
    
    # Modern digital styles
    "cyberpunk": VideoTheme(
        name="Cyberpunk",
        bg_color=(10, 10, 30),
        bg_gradient_end=(50, 0, 60),
        text_color="#00ff9f",
        accent_color="#ff00ff",
        title_font_size=90,
        body_font_size=52,
        use_gradient=True,
        add_border=True,
        border_color="#00ff9f",
        border_width=3,
        intro_bg=(20, 0, 40),
        outro_bg=(40, 0, 60),
        content_bg=(15, 10, 35)
    ),
    
    "futuristic": VideoTheme(
        name="Futuristic",
        bg_color=(0, 20, 40),
        bg_gradient_end=(0, 40, 80),
        text_color="#00d4ff",
        accent_color="#0099ff",
        title_font_size=88,
        body_font_size=50,
        use_gradient=True,
        intro_bg=(0, 15, 30),
        outro_bg=(0, 30, 60),
        content_bg=(0, 25, 50)
    ),
    
    "neon": VideoTheme(
        name="Neon",
        bg_color=(10, 10, 20),
        bg_gradient_end=(30, 0, 50),
        text_color="#39ff14",
        accent_color="#ff073a",
        title_font_size=92,
        body_font_size=54,
        use_gradient=True,
        intro_bg=(20, 10, 30),
        outro_bg=(40, 0, 60),
        content_bg=(15, 10, 25)
    ),
    
    # Natural & organic
    "nature": VideoTheme(
        name="Nature",
        bg_color=(34, 85, 51),
        bg_gradient_end=(85, 107, 47),
        text_color="#f5f5dc",
        accent_color="#8fbc8f",
        title_font_size=80,
        body_font_size=48,
        use_gradient=True,
        intro_bg=(40, 100, 60),
        outro_bg=(60, 120, 80),
        content_bg=(45, 90, 55)
    ),
    
    "dark": VideoTheme(
        name="Dark/Moody",
        bg_color=(20, 20, 30),
        bg_gradient_end=(40, 40, 50),
        text_color="#a0a0a0",
        accent_color="#606060",
        title_font_size=85,
        body_font_size=50,
        use_gradient=True,
        intro_bg=(15, 15, 25),
        outro_bg=(30, 30, 40),
        content_bg=(25, 25, 35)
    ),
    
    # Artistic styles
    "retro": VideoTheme(
        name="Retro/Vintage",
        bg_color=(218, 165, 32),
        bg_gradient_end=(205, 133, 63),
        text_color="#4a3728",
        accent_color="#8b4513",
        title_font_size=82,
        body_font_size=48,
        use_gradient=True,
        intro_bg=(240, 180, 60),
        outro_bg=(200, 150, 40),
        content_bg=(230, 170, 50)
    ),
    
    "paper": VideoTheme(
        name="Paper/Craft",
        bg_color=(250, 240, 230),
        bg_gradient_end=(245, 230, 215),
        text_color="#5c4033",
        accent_color="#8b7355",
        title_font_size=78,
        body_font_size=46,
        font_family="DejaVu-Sans",
        intro_bg=(255, 245, 235),
        outro_bg=(240, 230, 220),
        content_bg=(250, 240, 230)
    ),
    
    "watercolor": VideoTheme(
        name="Watercolor",
        bg_color=(135, 206, 250),
        bg_gradient_end=(176, 224, 230),
        text_color="#2f4f4f",
        accent_color="#4682b4",
        title_font_size=80,
        body_font_size=48,
        use_gradient=True,
        intro_bg=(150, 220, 255),
        outro_bg=(160, 200, 240),
        content_bg=(140, 210, 250)
    )
}


def get_theme(theme_name: str) -> VideoTheme:
    """Get a theme by name, fallback to modern."""
    return THEMES.get(theme_name, THEMES["modern"])


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color."""
    return '#{:02x}{:02x}{:02x}'.format(*rgb)
