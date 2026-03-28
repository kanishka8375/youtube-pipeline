"""Content generation module for script, title, and description creation."""

import json
from typing import Dict, List, Optional

from llm_providers import BaseLLMProvider, LLMProviderFactory


class ContentGenerator:
    """Generates video content using free LLM providers."""
    
    def __init__(self, provider: Optional[BaseLLMProvider] = None, provider_name: Optional[str] = None):
        """
        Initialize with a specific provider or auto-detect.
        
        Args:
            provider: Pre-configured LLM provider instance
            provider_name: Provider name to auto-create (ollama, groq, gemini, or auto)
        """
        if provider:
            self.provider = provider
        else:
            self.provider = LLMProviderFactory.create(provider_name)
    
    def generate_script(self, topic: str, duration_seconds: int = 60, style: str = "educational") -> Dict:
        """Generate a video script with segments for the given topic."""
        words = duration_seconds // 2
        
        prompt = f"""Create a {style} video script about "{topic}".
Target duration: {duration_seconds} seconds (~{words} words).

Format as JSON with this structure:
{{
    "title": " catchy YouTube title",
    "description": "SEO-friendly description (2-3 paragraphs)",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
    "segments": [
        {{
            "type": "intro|content|outro",
            "text": "narration text for this segment",
            "duration": estimated_seconds,
            "visual_suggestion": "what image/video to show"
        }}
    ]
}}

Rules:
- Hook viewers in first 5 seconds
- Keep sentences short and punchy for TTS
- Add [PAUSE] tags for natural breaks
- Include call-to-action in outro
"""
        
        response = self.provider.generate(
            prompt=prompt,
            system_prompt="You are an expert YouTube content creator. Output valid JSON only.",
            json_mode=True
        )
        
        try:
            return json.loads(response.content)
        except json.JSONDecodeError as e:
            # Retry with explicit JSON-only instruction
            print(f"JSON parse error, retrying... {e}")
            response = self.provider.generate(
                prompt=prompt + "\n\nCRITICAL: Return ONLY raw JSON. No markdown, no explanations.",
                system_prompt="You are an expert YouTube content creator. Output valid JSON only.",
                json_mode=True
            )
            return json.loads(response.content)
    
    def generate_thumbnail_ideas(self, title: str, script: str) -> List[str]:
        """Generate thumbnail text and concept ideas."""
        prompt = f"""Generate 3 thumbnail concepts for a YouTube video.

Title: {title}
Script: {script[:500]}...

For each thumbnail provide:
1. Main text (3-5 words, bold, high contrast)
2. Background concept
3. Face expression (if applicable)

Format as a simple list."""
        
        response = self.provider.generate(prompt=prompt)
        return response.content.split("\n")
    
    def generate_title_variants(self, topic: str, base_title: str, count: int = 3) -> List[str]:
        """Generate title variants for A/B testing ideas."""
        prompt = f"""Generate {count} clickable YouTube title variations.

Topic: {topic}
Current title: {base_title}

Create titles using these formulas:
- How to...
- X Things You Didn't Know About...
- The Truth About...
- Why ... Is [Surprising/Wrong/Changing]
- I Tried ... For 30 Days

Format as a numbered list."""
        
        response = self.provider.generate(prompt=prompt)
        return response.content.split("\n")


if __name__ == "__main__":
    # Test with auto-selected provider
    gen = ContentGenerator()
    print(f"Using provider: {type(gen.provider).__name__}")
    
    result = gen.generate_script("The history of coffee", duration_seconds=45)
    print(json.dumps(result, indent=2))
