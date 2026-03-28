"""Background music generator using free AI models."""

import os
import re
import time
import tempfile
from typing import Optional, List, Dict
from pathlib import Path
from dataclasses import dataclass

import requests
import numpy as np
from pydub import AudioSegment


@dataclass
class MusicConfig:
    """Configuration for music generation."""
    duration: int = 30  # seconds
    genre: str = "ambient"
    mood: str = "calm"
    tempo: str = "medium"  # slow, medium, fast
    instrumental: bool = True


class FreeMusicGenerator:
    """Generate background music using free AI models."""
    
    # Genre/mood to prompt mappings
    STYLE_PROMPTS = {
        "ambient": {
            "calm": "peaceful ambient music, soft pads, relaxing atmosphere",
            "upbeat": "light ambient, gentle electronic, positive energy",
            "dark": "dark ambient, mysterious, ethereal atmosphere",
            "epic": "cinematic ambient, vast soundscape, inspiring"
        },
        "electronic": {
            "calm": "chill electronic, lo-fi beats, downtempo",
            "upbeat": "energetic electronic, synthwave, upbeat tempo",
            "dark": "dark techno, industrial electronic, intense",
            "epic": "epic electronic, progressive, uplifting"
        },
        "cinematic": {
            "calm": "soft cinematic, gentle strings, peaceful",
            "upbeat": "adventure cinematic, orchestral, exciting",
            "dark": "tense cinematic, dramatic, suspense",
            "epic": "epic orchestral, heroic, inspiring, trailer music"
        },
        "lofi": {
            "calm": "lo-fi hip hop, chill beats, study music, rain sounds",
            "upbeat": "lo-fi house, chillhop, groovy",
            "dark": "dark lofi, melancholic, slow beats",
            "epic": "orchestral lofi, grand beats, majestic"
        },
        "piano": {
            "calm": "solo piano, gentle melody, peaceful",
            "upbeat": "upbeat piano, happy melody, bright",
            "dark": "minor key piano, emotional, dramatic",
            "epic": "grand piano, powerful chords, cinematic"
        }
    }
    
    def __init__(self, output_dir: str = "temp/music"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(tempfile.gettempdir()) / "music_gen"
        self.temp_dir.mkdir(exist_ok=True)
    
    def _get_prompt(self, config: MusicConfig) -> str:
        """Generate descriptive prompt for music."""
        base = self.STYLE_PROMPTS.get(config.genre, self.STYLE_PROMPTS["ambient"])
        mood_desc = base.get(config.mood, base["calm"])
        
        tempo_desc = {
            "slow": "slow tempo, relaxed",
            "medium": "medium tempo, steady",
            "fast": "fast tempo, energetic"
        }.get(config.tempo, "medium tempo")
        
        prompt = f"{mood_desc}, {tempo_desc}, instrumental background music"
        return prompt
    
    def generate_music(self, config: Optional[MusicConfig] = None, 
                       output_path: Optional[str] = None,
                       provider: str = "local") -> str:
        """
        Generate background music using free models.
        
        Args:
            config: Music configuration
            output_path: Output file path
            provider: "local" (MusicGen), "huggingface" (API), or "suno" (if available)
        """
        config = config or MusicConfig()
        
        if output_path is None:
            output_path = self.output_dir / f"bgm_{config.genre}_{config.mood}_{int(time.time())}.wav"
        else:
            output_path = Path(output_path)
        
        if provider == "local":
            return self._generate_local(config, str(output_path))
        elif provider == "huggingface":
            return self._generate_hf_api(config, str(output_path))
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def _generate_local(self, config: MusicConfig, output_path: str) -> str:
        """Generate using local MusicGen (Meta's Audiocraft)."""
        try:
            # Try to import audiocraft
            from audiocraft.models import MusicGen
            from audiocraft.data.audio import audio_write
            
            print("Loading MusicGen model...")
            model = MusicGen.get_pretrained("small")
            
            # Set generation parameters
            model.set_generation_params(
                duration=config.duration,
                top_k=250,
                top_p=0.95,
                temperature=1.0
            )
            
            prompt = self._get_prompt(config)
            print(f"Generating music: {prompt}")
            
            # Generate
            wav = model.generate([prompt])
            
            # Save
            audio_write(
                Path(output_path).stem,
                wav[0].cpu(),
                model.sample_rate,
                strategy="loudness",
                loudness_compressor=True
            )
            
            return output_path
            
        except ImportError:
            print("AudioCraft not installed. Falling back to HuggingFace API...")
            return self._generate_hf_api(config, output_path)
    
    def _generate_hf_api(self, config: MusicConfig, output_path: str) -> str:
        """Generate using Hugging Face Inference API (free tier)."""
        # Using Facebook's MusicGen via Hugging Face
        api_url = "https://api-inference.huggingface.co/models/facebook/musicgen-small"
        
        # Note: This requires a HF token for prolonged use, but has free tier
        headers = {}
        hf_token = os.getenv("HF_API_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
        
        prompt = self._get_prompt(config)
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "duration": min(config.duration, 30),  # HF limit
                "guidance_scale": 3.0
            }
        }
        
        print(f"Generating music via HuggingFace API: {prompt}")
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        
        if response.status_code == 200:
            # Save audio bytes
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
        else:
            # Fallback to creating a simple ambient tone
            print(f"API failed ({response.status_code}), generating simple tone...")
            return self._generate_simple_tone(config, output_path)
    
    def _generate_simple_tone(self, config: MusicConfig, output_path: str) -> str:
        """Generate simple ambient tones as fallback."""
        try:
            from pydub.generators import Sine, Square
            
            duration_ms = config.duration * 1000
            
            # Create layered ambient sound
            base_freq = {"ambient": 220, "electronic": 130, "cinematic": 110, 
                        "lofi": 140, "piano": 261}.get(config.genre, 220)
            
            # Generate multiple tones
            tones = []
            for i, harmonic in enumerate([1, 1.5, 2]):
                freq = base_freq * harmonic
                # Vary volume for each layer
                vol = -20 - (i * 5)
                tone = Sine(freq).to_audio_segment(duration=duration_ms).apply_gain(vol)
                tones.append(tone)
            
            # Mix together
            mixed = tones[0]
            for tone in tones[1:]:
                mixed = mixed.overlay(tone)
            
            # Fade in/out
            mixed = mixed.fade_in(2000).fade_out(2000)
            
            # Export
            mixed.export(output_path, format="wav")
            return output_path
            
        except Exception as e:
            print(f"Tone generation failed: {e}")
            # Last resort - create silence
            silence = AudioSegment.silent(duration=config.duration * 1000)
            silence.export(output_path, format="wav")
            return output_path
    
    def loop_music(self, music_path: str, target_duration: int, 
                   output_path: Optional[str] = None) -> str:
        """Loop music to match video duration with smooth transitions."""
        if output_path is None:
            output_path = Path(music_path).parent / f"looped_{Path(music_path).name}"
        
        audio = AudioSegment.from_file(music_path)
        
        # Calculate loops needed
        target_ms = target_duration * 1000
        loops_needed = int(target_ms / len(audio)) + 1
        
        # Create looped version
        looped = audio
        for _ in range(loops_needed - 1):
            # Crossfade for smooth loop
            looped = looped.append(audio, crossfade=2000)
        
        # Trim to exact duration
        looped = looped[:target_ms]
        
        # Fade out at end
        looped = looped.fade_out(3000)
        
        looped.export(str(output_path), format="mp3")
        return str(output_path)
    
    def adjust_volume(self, music_path: str, volume_db: float = -20,
                      output_path: Optional[str] = None) -> str:
        """Adjust music volume (default -20dB for background)."""
        if output_path is None:
            output_path = Path(music_path).parent / f"quiet_{Path(music_path).name}"
        
        audio = AudioSegment.from_file(music_path)
        adjusted = audio.apply_gain(volume_db)
        adjusted.export(str(output_path), format="mp3")
        return str(output_path)


class MusicLibrary:
    """Simple royalty-free music library (fallback when AI generation fails)."""
    
    # URLs to free music resources
    FREE_RESOURCES = {
        "freesound": "https://freesound.org",
        "incompetech": "https://incompetech.com/music/royalty-free/music.html",
        "ccmixter": "http://ccmixter.org",
        "freemusicarchive": "https://freemusicarchive.org"
    }
    
    def __init__(self, library_dir: str = "assets/music"):
        self.library_dir = Path(library_dir)
        self.library_dir.mkdir(parents=True, exist_ok=True)
    
    def list_tracks(self) -> List[Dict]:
        """List available tracks in library."""
        tracks = []
        for ext in ["mp3", "wav", "ogg"]:
            for file in self.library_dir.glob(f"*.{ext}"):
                tracks.append({
                    "name": file.stem,
                    "path": str(file),
                    "duration": self._get_duration(file)
                })
        return tracks
    
    def _get_duration(self, file: Path) -> float:
        """Get audio file duration in seconds."""
        try:
            audio = AudioSegment.from_file(file)
            return len(audio) / 1000
        except:
            return 0
    
    def get_track(self, genre: str = "ambient", mood: str = "calm") -> Optional[str]:
        """Get a matching track from library if available."""
        tracks = self.list_tracks()
        
        # Simple matching by name
        for track in tracks:
            name_lower = track["name"].lower()
            if genre.lower() in name_lower or mood.lower() in name_lower:
                return track["path"]
        
        # Return first available if no match
        if tracks:
            return tracks[0]["path"]
        
        return None


if __name__ == "__main__":
    # Test music generation
    gen = FreeMusicGenerator()
    
    config = MusicConfig(
        duration=15,
        genre="ambient",
        mood="calm",
        tempo="medium"
    )
    
    print("Testing music generation...")
    
    # Try local first, fallback to HF
    try:
        music_path = gen.generate_music(config, provider="local")
        print(f"Generated: {music_path}")
    except Exception as e:
        print(f"Local failed: {e}")
        music_path = gen.generate_music(config, provider="huggingface")
        print(f"Generated via API: {music_path}")
    
    # Test looping
    if music_path:
        looped = gen.loop_music(music_path, target_duration=60)
        print(f"Looped version: {looped}")
