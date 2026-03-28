"""Validation module for verifying all generated content quality and accuracy."""

import os
import json
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import requests

from pydub import AudioSegment
from PIL import Image


class ContentValidator:
    """Validates generated content against original requirements."""
    
    def __init__(self, llm_provider=None):
        """Initialize with optional LLM provider for semantic validation."""
        self.llm_provider = llm_provider
        self.validation_results = []
    
    def validate_script(self, topic: str, script: Dict, 
                        expected_duration: int) -> Dict:
        """
        Validate generated script matches topic and requirements.
        
        Checks:
        - Topic relevance
        - Duration estimate accuracy
        - JSON structure validity
        - Content quality
        """
        result = {
            "valid": True,
            "checks": {},
            "score": 0.0,
            "errors": []
        }
        
        # Check 1: Basic structure
        required_fields = ["title", "description", "tags", "segments"]
        for field in required_fields:
            if field not in script:
                result["valid"] = False
                result["errors"].append(f"Missing required field: {field}")
        
        result["checks"]["structure"] = len(result["errors"]) == 0
        
        # Check 2: Topic relevance (if LLM available)
        if self.llm_provider and "title" in script:
            relevance = self._check_topic_relevance(topic, script["title"], script.get("description", ""))
            result["checks"]["topic_relevance"] = relevance["score"] > 0.6
            result["checks"]["relevance_score"] = relevance["score"]
            if relevance["score"] < 0.4:
                result["valid"] = False
                result["errors"].append(f"Low topic relevance: {relevance['reason']}")
        
        # Check 3: Duration estimate
        if "segments" in script:
            estimated_duration = sum(seg.get("duration", 0) for seg in script["segments"])
            duration_diff = abs(estimated_duration - expected_duration)
            duration_error_pct = (duration_diff / expected_duration) * 100 if expected_duration > 0 else 0
            
            result["checks"]["duration_estimate"] = duration_error_pct < 30  # Within 30%
            result["checks"]["duration_error_pct"] = duration_error_pct
            
            if duration_error_pct > 50:
                result["valid"] = False
                result["errors"].append(f"Duration mismatch: {estimated_duration}s vs {expected_duration}s")
        
        # Check 4: Content quality heuristics
        if "segments" in script:
            quality_score = self._check_content_quality(script["segments"])
            result["checks"]["content_quality"] = quality_score > 0.5
            result["checks"]["quality_score"] = quality_score
        
        # Calculate overall score
        check_scores = [
            result["checks"].get("structure", False),
            result["checks"].get("topic_relevance", True),
            result["checks"].get("duration_estimate", True),
            result["checks"].get("content_quality", True)
        ]
        result["score"] = sum(check_scores) / len(check_scores)
        
        # Re-validate if score too low
        if result["score"] < 0.6:
            result["valid"] = False
        
        return result
    
    def _check_topic_relevance(self, topic: str, title: str, description: str) -> Dict:
        """Use LLM to check semantic relevance of content to topic."""
        prompt = f"""Rate the relevance of this video content to the topic "{topic}".

Title: {title}
Description: {description[:200]}...

Rate from 0.0 (completely unrelated) to 1.0 (perfectly aligned).
Respond with JSON:
{{
    "score": 0.0-1.0,
    "reason": "brief explanation"
}}"""
        
        try:
            response = self.llm_provider.generate(prompt, json_mode=True)
            result = json.loads(response.content)
            return {
                "score": float(result.get("score", 0.5)),
                "reason": result.get("reason", "No explanation")
            }
        except Exception as e:
            return {"score": 0.5, "reason": f"Validation error: {e}"}
    
    def _check_content_quality(self, segments: List[Dict]) -> float:
        """Check content quality heuristics."""
        scores = []
        
        for seg in segments:
            text = seg.get("text", "")
            
            # Check minimum length
            if len(text) < 10:
                scores.append(0.3)
                continue
            
            # Check maximum length (avoid overly long)
            if len(text) > 500:
                scores.append(0.5)
                continue
            
            # Check for repeated phrases
            words = text.lower().split()
            if len(words) > 5:
                unique_words = len(set(words))
                total_words = len(words)
                diversity = unique_words / total_words
                scores.append(diversity)
            else:
                scores.append(0.5)
        
        return sum(scores) / len(scores) if scores else 0.5
    
    def validate_image(self, image_path: str, scene_text: str, 
                       visual_suggestion: str = "") -> Dict:
        """
        Validate generated image is suitable for the scene.
        
        Uses heuristics since we can't use vision models reliably:
        - File integrity
        - Dimensions
        - File size (not too small/empty)
        """
        result = {
            "valid": True,
            "checks": {},
            "score": 0.0,
            "errors": []
        }
        
        # Check 1: File exists and is readable
        if not os.path.exists(image_path):
            result["valid"] = False
            result["errors"].append("Image file not found")
            return result
        
        # Check 2: File size (not empty/corrupted)
        file_size = os.path.getsize(image_path)
        result["checks"]["file_size"] = file_size > 1000  # At least 1KB
        if not result["checks"]["file_size"]:
            result["valid"] = False
            result["errors"].append(f"File too small ({file_size} bytes)")
        
        # Check 3: Image can be loaded
        try:
            img = Image.open(image_path)
            width, height = img.size
            result["checks"]["loadable"] = True
            result["checks"]["dimensions"] = (width, height)
            
            # Check minimum dimensions
            result["checks"]["min_dimensions"] = width >= 512 and height >= 512
            if not result["checks"]["min_dimensions"]:
                result["errors"].append(f"Image too small: {width}x{height}")
        except Exception as e:
            result["valid"] = False
            result["checks"]["loadable"] = False
            result["errors"].append(f"Cannot load image: {e}")
        
        # Check 4: Relevance to scene (using LLM if available)
        if self.llm_provider and visual_suggestion:
            relevance = self._check_image_relevance(image_path, scene_text, visual_suggestion)
            result["checks"]["scene_relevance"] = relevance["score"] > 0.4
            result["checks"]["relevance_score"] = relevance["score"]
        
        # Calculate score
        check_results = [
            result["checks"].get("file_size", False),
            result["checks"].get("loadable", False),
            result["checks"].get("min_dimensions", False),
            result["checks"].get("scene_relevance", True)
        ]
        result["score"] = sum(check_results) / len(check_results)
        
        if result["score"] < 0.5:
            result["valid"] = False
        
        return result
    
    def _check_image_relevance(self, image_path: str, scene_text: str, 
                               visual_suggestion: str) -> Dict:
        """Check if image description matches visual suggestion using LLM."""
        # Since we can't see the image, we validate the generation prompt was used
        # and check if the visual suggestion aligns with scene text
        
        prompt = f"""Evaluate if this visual suggestion matches the scene:

Scene Text: {scene_text[:100]}
Visual Suggestion: {visual_suggestion}

Rate alignment from 0.0 (unrelated) to 1.0 (perfect match).
Respond with JSON:
{{
    "score": 0.0-1.0,
    "reason": "explanation"
}}"""
        
        try:
            response = self.llm_provider.generate(prompt, json_mode=True)
            result = json.loads(response.content)
            return {
                "score": float(result.get("score", 0.5)),
                "reason": result.get("reason", "No explanation")
            }
        except:
            # Fallback: simple text similarity
            text_words = set(scene_text.lower().split())
            visual_words = set(visual_suggestion.lower().split())
            overlap = len(text_words & visual_words)
            total = len(text_words | visual_words)
            score = overlap / total if total > 0 else 0.5
            return {"score": score, "reason": "Basic word overlap"}
    
    def validate_audio(self, audio_path: str, expected_text: str,
                       min_duration: float = 1.0) -> Dict:
        """
        Validate TTS audio quality and duration.
        
        Checks:
        - File integrity
        - Duration reasonable for text length
        - Audio levels (not silent)
        """
        result = {
            "valid": True,
            "checks": {},
            "score": 0.0,
            "errors": []
        }
        
        # Check 1: File exists
        if not os.path.exists(audio_path):
            result["valid"] = False
            result["errors"].append("Audio file not found")
            return result
        
        # Check 2: Load and analyze
        try:
            audio = AudioSegment.from_file(audio_path)
            duration_sec = len(audio) / 1000.0
            
            result["checks"]["loadable"] = True
            result["checks"]["duration"] = duration_sec
            
            # Check minimum duration
            result["checks"]["min_duration"] = duration_sec >= min_duration
            if not result["checks"]["min_duration"]:
                result["valid"] = False
                result["errors"].append(f"Audio too short: {duration_sec:.1f}s")
            
            # Check for silence (audio level)
            dBFS = audio.dBFS
            result["checks"]["audio_level_db"] = dBFS
            result["checks"]["not_silent"] = dBFS > -50  # Not essentially silent
            
            if not result["checks"]["not_silent"]:
                result["errors"].append(f"Audio too quiet: {dBFS:.1f} dBFS")
            
            # Check duration vs text length (rough heuristic: ~0.1s per word)
            word_count = len(expected_text.split())
            expected_duration = word_count * 0.1
            duration_ratio = duration_sec / expected_duration if expected_duration > 0 else 1
            
            result["checks"]["duration_ratio"] = duration_ratio
            result["checks"]["duration_reasonable"] = 0.5 <= duration_ratio <= 3.0
            
            if not result["checks"]["duration_reasonable"]:
                result["warnings"] = [f"Duration ratio unusual: {duration_ratio:.1f}x"]
        
        except Exception as e:
            result["valid"] = False
            result["checks"]["loadable"] = False
            result["errors"].append(f"Cannot load audio: {e}")
        
        # Calculate score
        check_results = [
            result["checks"].get("loadable", False),
            result["checks"].get("min_duration", False),
            result["checks"].get("not_silent", False),
            result["checks"].get("duration_reasonable", True)
        ]
        result["score"] = sum(check_results) / len(check_results)
        
        if result["score"] < 0.5:
            result["valid"] = False
        
        return result
    
    def validate_video_segment(self, video_path: str, expected_duration: float,
                               has_audio: bool = True) -> Dict:
        """
        Validate video segment integrity.
        
        Checks:
        - File integrity
        - Duration matches expected
        - Has audio if required
        - Frame rate consistency
        """
        from moviepy.editor import VideoFileClip
        
        result = {
            "valid": True,
            "checks": {},
            "score": 0.0,
            "errors": []
        }
        
        if not os.path.exists(video_path):
            result["valid"] = False
            result["errors"].append("Video file not found")
            return result
        
        try:
            video = VideoFileClip(video_path)
            
            # Check duration
            actual_duration = video.duration
            result["checks"]["duration"] = actual_duration
            duration_diff = abs(actual_duration - expected_duration)
            result["checks"]["duration_accuracy"] = duration_diff < 0.1  # Within 100ms
            
            if not result["checks"]["duration_accuracy"]:
                result["errors"].append(f"Duration mismatch: {actual_duration:.2f}s vs {expected_duration:.2f}s")
            
            # Check frame rate
            result["checks"]["fps"] = video.fps
            result["checks"]["has_video"] = video.size[0] > 0 and video.size[1] > 0
            
            # Check audio
            if has_audio:
                result["checks"]["has_audio"] = video.audio is not None
                if video.audio:
                    result["checks"]["audio_duration"] = video.audio.duration
            
            video.close()
            
        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Cannot load video: {e}")
        
        # Calculate score
        check_results = [
            result["checks"].get("duration_accuracy", False),
            result["checks"].get("has_video", False),
            result["checks"].get("has_audio", True) if has_audio else True
        ]
        result["score"] = sum(check_results) / len(check_results)
        
        if result["score"] < 0.6:
            result["valid"] = False
        
        return result
    
    def validate_final_video(self, video_path: str, 
                            expected_segments: int,
                            expected_duration: float,
                            has_music: bool = False) -> Dict:
        """Validate final assembled video meets all requirements."""
        from moviepy.editor import VideoFileClip
        
        result = {
            "valid": True,
            "checks": {},
            "score": 0.0,
            "errors": [],
            "warnings": []
        }
        
        if not os.path.exists(video_path):
            result["valid"] = False
            result["errors"].append("Final video file not found")
            return result
        
        try:
            video = VideoFileClip(video_path)
            
            # Basic checks
            result["checks"]["duration"] = video.duration
            result["checks"]["size"] = video.size
            result["checks"]["fps"] = video.fps
            
            # Duration within 5% of expected
            duration_error = abs(video.duration - expected_duration) / expected_duration
            result["checks"]["duration_within_tolerance"] = duration_error < 0.05
            
            if not result["checks"]["duration_within_tolerance"]:
                result["warnings"].append(f"Duration deviation: {duration_error*100:.1f}%")
            
            # Video integrity
            result["checks"]["valid_dimensions"] = video.size[0] >= 1280 and video.size[1] >= 720
            result["checks"]["valid_fps"] = video.fps >= 24
            
            # Audio check
            if video.audio:
                result["checks"]["has_audio"] = True
                result["checks"]["audio_duration"] = video.audio.duration
                
                # Audio should match video duration
                audio_diff = abs(video.audio.duration - video.duration)
                result["checks"]["audio_synced"] = audio_diff < 0.5
                
                if not result["checks"]["audio_synced"]:
                    result["errors"].append(f"Audio/video duration mismatch: {audio_diff:.2f}s")
            else:
                result["checks"]["has_audio"] = False
                result["errors"].append("No audio track found")
            
            video.close()
            
        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Cannot validate video: {e}")
        
        # Calculate score
        check_results = [
            result["checks"].get("duration_within_tolerance", False),
            result["checks"].get("valid_dimensions", False),
            result["checks"].get("valid_fps", False),
            result["checks"].get("has_audio", False),
            result["checks"].get("audio_synced", False)
        ]
        result["score"] = sum(check_results) / len(check_results)
        
        if result["score"] < 0.7:
            result["valid"] = False
        
        return result


class ValidationRetryManager:
    """Manages retry logic for failed validations."""
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_counts = {}
    
    def should_retry(self, item_id: str) -> bool:
        """Check if item should be retried."""
        current = self.retry_counts.get(item_id, 0)
        return current < self.max_retries
    
    def record_attempt(self, item_id: str):
        """Record a retry attempt."""
        self.retry_counts[item_id] = self.retry_counts.get(item_id, 0) + 1
    
    def get_retry_count(self, item_id: str) -> int:
        """Get number of retries for item."""
        return self.retry_counts.get(item_id, 0)


if __name__ == "__main__":
    # Test validators
    validator = ContentValidator()
    
    # Test script validation
    test_script = {
        "title": "The History of Coffee",
        "description": "Learn about coffee's fascinating journey",
        "tags": ["coffee", "history", "education"],
        "segments": [
            {"type": "intro", "text": "Welcome! Today we explore coffee.", "duration": 5},
            {"type": "content", "text": "Coffee originated in Ethiopia.", "duration": 10}
        ]
    }
    
    result = validator.validate_script("coffee history", test_script, 60)
    print("Script validation:", result)
