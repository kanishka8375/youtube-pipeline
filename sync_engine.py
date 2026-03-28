"""Precision synchronization engine for audio-visual-music alignment."""

import os
import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment
from moviepy.editor import AudioFileClip, VideoFileClip


@dataclass
class SyncConfig:
    """Configuration for precise synchronization."""
    fps: int = 30
    frame_duration: float = 1/30  # seconds per frame
    audio_buffer_ms: int = 50  # small buffer for audio processing
    music_bpm: int = 120  # beats per minute for music sync
    beat_alignment: bool = True  # align scene transitions to beats
    crossfade_duration: float = 0.3  # seconds for smooth transitions


class SyncEngine:
    """Ensures precise synchronization between audio, video, and music."""
    
    def __init__(self, config: Optional[SyncConfig] = None):
        self.config = config or SyncConfig()
        self.segments_timing: List[Dict] = []
    
    def calculate_segment_durations(self, audio_paths: List[str], 
                                    target_total: Optional[float] = None) -> List[float]:
        """
        Calculate precise durations for each segment based on actual audio files.
        Returns frame-aligned durations.
        """
        durations = []
        total_duration = 0
        
        for path in audio_paths:
            if os.path.exists(path):
                # Get exact audio duration using pydub (more accurate)
                audio = AudioSegment.from_file(path)
                duration_sec = len(audio) / 1000.0
                
                # Round to nearest frame for perfect sync
                frames = round(duration_sec * self.config.fps)
                frame_aligned_duration = frames / self.config.fps
                
                durations.append(frame_aligned_duration)
                total_duration += frame_aligned_duration
            else:
                durations.append(0)
        
        # If target total specified, adjust proportionally
        if target_total and total_duration > 0:
            ratio = target_total / total_duration
            durations = [d * ratio for d in durations]
            # Re-align to frames
            durations = [round(d * self.config.fps) / self.config.fps for d in durations]
        
        return durations
    
    def align_to_beats(self, duration: float, bpm: Optional[int] = None) -> float:
        """Align duration to nearest music beat for seamless transitions."""
        bpm = bpm or self.config.music_bpm
        beat_duration = 60.0 / bpm  # seconds per beat
        
        # Round to nearest beat
        beats = round(duration / beat_duration)
        aligned_duration = beats * beat_duration
        
        # Ensure at least one beat
        if aligned_duration < beat_duration:
            aligned_duration = beat_duration
        
        return aligned_duration
    
    def create_beat_matched_music(self, music_path: str, target_duration: float,
                                   output_path: str, bpm: Optional[int] = None) -> str:
        """
        Create music loop that perfectly matches video duration on beat boundaries.
        Ensures music starts and ends on beat for seamless feel.
        """
        bpm = bpm or self.config.music_bpm
        beat_duration = 60.0 / bpm
        
        # Load music
        music = AudioSegment.from_file(music_path)
        music_duration = len(music) / 1000.0
        
        # Calculate how many beats we need
        total_beats = math.ceil(target_duration / beat_duration)
        aligned_duration = total_beats * beat_duration
        
        # Create loop
        if music_duration >= aligned_duration:
            # Trim to exact beat boundary
            trim_ms = int(aligned_duration * 1000)
            looped = music[:trim_ms]
        else:
            # Loop until we have enough
            loops_needed = math.ceil(aligned_duration / music_duration)
            looped = music
            for _ in range(loops_needed - 1):
                # Crossfade at beat boundaries for smooth loop
                crossfade_ms = int(self.config.crossfade_duration * 1000)
                looped = looped.append(music, crossfade=crossfade_ms)
            
            # Trim to exact beat boundary
            target_ms = int(aligned_duration * 1000)
            looped = looped[:target_ms]
        
        # Fade in/out at beat boundaries
        fade_ms = int(beat_duration * 1000)  # One beat fade
        looped = looped.fade_in(min(fade_ms, 500)).fade_out(min(fade_ms, 1000))
        
        # Export
        looped.export(output_path, format="mp3")
        return output_path
    
    def sync_audio_levels(self, voice_path: str, music_path: str,
                         output_path: str,
                         voice_db: float = 0, 
                         music_db: float = -18) -> str:
        """
        Mix voice and music with precise level control.
        Ensures voice is always audible above background music.
        """
        # Load audio
        voice = AudioSegment.from_file(voice_path)
        music = AudioSegment.from_file(music_path)
        
        # Match durations
        target_duration = max(len(voice), len(music))
        
        if len(voice) < target_duration:
            # Extend voice with silence (for gaps between speech)
            silence = AudioSegment.silent(duration=target_duration - len(voice))
            voice = voice + silence
        
        if len(music) < target_duration:
            # Loop music
            while len(music) < target_duration:
                music = music.append(music, crossfade=100)
            music = music[:target_duration]
        else:
            music = music[:target_duration]
        
        # Apply levels
        voice = voice.apply_gain(voice_db)
        music = music.apply_gain(music_db)
        
        # Duck music when voice is present (sidechain compression simulation)
        voice_segments = self._detect_voice_segments(voice)
        music = self._duck_audio(music, voice_segments)
        
        # Mix
        mixed = voice.overlay(music)
        
        # Export
        mixed.export(output_path, format="mp3")
        return output_path
    
    def _detect_voice_segments(self, audio: AudioSegment, 
                               threshold_db: float = -40) -> List[Tuple[int, int]]:
        """Detect segments where voice is present (above threshold)."""
        segments = []
        chunk_ms = 50  # Check every 50ms
        
        current_start = None
        
        for i in range(0, len(audio), chunk_ms):
            chunk = audio[i:i + chunk_ms]
            rms = chunk.rms
            
            # Convert to dB
            if rms > 0:
                db = 20 * math.log10(rms / 32768)
            else:
                db = -96
            
            if db > threshold_db:
                if current_start is None:
                    current_start = i
            else:
                if current_start is not None:
                    segments.append((current_start, i))
                    current_start = None
        
        # Close final segment
        if current_start is not None:
            segments.append((current_start, len(audio)))
        
        return segments
    
    def _duck_audio(self, music: AudioSegment, 
                    voice_segments: List[Tuple[int, int]],
                    duck_amount_db: float = -12) -> AudioSegment:
        """Reduce music volume during voice segments."""
        if not voice_segments:
            return music
        
        # Apply ducking with fade in/out
        result = music
        
        for start_ms, end_ms in voice_segments:
            # Add padding for fade
            fade_ms = 100
            duck_start = max(0, start_ms - fade_ms)
            duck_end = min(len(music), end_ms + fade_ms)
            
            # Get segment
            before = result[:duck_start]
            during = result[duck_start:duck_end]
            after = result[duck_end:]
            
            # Apply ducking with smooth fade
            during = during.apply_gain(duck_amount_db)
            during = during.fade_in(fade_ms).fade_out(fade_ms)
            
            # Recombine
            result = before + during + after
        
        return result
    
    def verify_sync(self, video_path: str, expected_duration: float,
                   tolerance_ms: int = 50) -> Dict:
        """Verify final video has correct duration and sync."""
        if not os.path.exists(video_path):
            return {"error": "Video file not found"}
        
        video = VideoFileClip(video_path)
        actual_duration = video.duration
        video.close()
        
        diff_ms = abs(actual_duration - expected_duration) * 1000
        
        result = {
            "expected_duration": expected_duration,
            "actual_duration": actual_duration,
            "difference_ms": diff_ms,
            "is_synced": diff_ms <= tolerance_ms,
            "tolerance_ms": tolerance_ms
        }
        
        return result
    
    def create_sync_report(self, segments: List[Dict], 
                          audio_paths: List[str],
                          output_path: str) -> Dict:
        """Generate detailed sync report for debugging."""
        report = {
            "total_segments": len(segments),
            "segments": [],
            "total_duration": 0
        }
        
        for i, (seg, audio_path) in enumerate(zip(segments, audio_paths)):
            if os.path.exists(audio_path):
                audio = AudioSegment.from_file(audio_path)
                duration = len(audio) / 1000.0
                
                seg_report = {
                    "index": i,
                    "type": seg.get("type", "content"),
                    "text_length": len(seg.get("text", "")),
                    "audio_duration": duration,
                    "frames": round(duration * self.config.fps)
                }
                
                report["segments"].append(seg_report)
                report["total_duration"] += duration
        
        # Save report
        import json
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report


class FrameAccurateAssembler:
    """Video assembler with frame-accurate timing control."""
    
    def __init__(self, fps: int = 30):
        self.fps = fps
        self.frame_duration = 1.0 / fps
    
    def trim_to_exact_frames(self, clip, target_duration: float):
        """Trim clip to exact frame-aligned duration."""
        target_frames = round(target_duration * self.fps)
        exact_duration = target_frames * self.frame_duration
        return clip.subclip(0, exact_duration)
    
    def calculate_crossfade_frames(self, duration_seconds: float) -> int:
        """Calculate crossfade in frames."""
        return round(duration_seconds * self.fps)


if __name__ == "__main__":
    # Test sync engine
    engine = SyncEngine()
    
    # Test beat alignment
    duration = 5.3
    aligned = engine.align_to_beats(duration, bpm=128)
    print(f"Original: {duration}s, Aligned to 128 BPM: {aligned}s")
    
    # Test frame alignment
    durations = engine.calculate_segment_durations(["temp/audio/segment_000.mp3"])
    print(f"Frame-aligned durations: {durations}")
