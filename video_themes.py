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
