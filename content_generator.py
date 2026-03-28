"""Content generation module for script, title, and description creation."""

import json
from typing import Dict, List, Optional
import requests

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
            self.provider = self._create_provider_with_fallback(provider_name)
    
    def _create_provider_with_fallback(self, provider_name: Optional[str]) -> BaseLLMProvider:
        """Create provider with automatic fallback on failure."""
        # Try requested provider first
        if provider_name and provider_name != "auto":
            try:
                provider = LLMProviderFactory.create(provider_name)
                if provider.is_available():
                    print(f"Using provider: {provider_name}")
                    return provider
            except Exception as e:
                print(f"{provider_name} not available: {e}")
        
        # Try providers in order of preference
        providers_to_try = ["ollama", "groq", "gemini"]
        
        for name in providers_to_try:
            try:
                provider = LLMProviderFactory.create(name)
                if provider.is_available():
                    print(f"Auto-selected provider: {name}")
                    return provider
            except Exception as e:
                print(f"  {name} not available: {e}")
                continue
        
        raise RuntimeError("No LLM provider available. Options:\n"
                          "- Install Ollama: https://ollama.com\n"
                          "- Set GROQ_API_KEY for Groq\n"
                          "- Set GEMINI_API_KEY for Gemini")
    
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
        
        # Handle empty/None response - critical to avoid JSON decode error
        content_raw = getattr(response, 'content', None)
        if not content_raw or not str(content_raw).strip():
            print("Warning: Empty/None response from LLM, using fallback script")
            return self._create_fallback_script(topic, duration_seconds)
        
        # Clean up response - remove markdown code blocks if present
        content = response.content.strip()
        if content.startswith('```'):
            # Extract content from markdown code block
            lines = content.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].startswith('```'):
                lines = lines[:-1]
            content = '\n'.join(lines).strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Response content: {content[:200]}...")
            
            # Retry with explicit JSON-only instruction
            response = self.provider.generate(
                prompt=prompt + "\n\nCRITICAL: Return ONLY raw JSON. No markdown, no explanations.",
                system_prompt="You are an expert YouTube content creator. Output valid JSON only.",
                json_mode=True
            )
            
            content_raw = getattr(response, 'content', None)
            if not content_raw or not str(content_raw).strip():
                return self._create_fallback_script(topic, duration_seconds)
            
            content = response.content.strip()
            if content.startswith('```'):
                lines = content.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].startswith('```'):
                    lines = lines[:-1]
                content = '\n'.join(lines).strip()
            
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                print("Retry failed, using fallback script")
                return self._create_fallback_script(topic, duration_seconds)
    

    def _create_fallback_script(self, topic: str, duration_seconds: int) -> Dict:
        """Create a basic fallback script when LLM fails."""
        words = duration_seconds // 2
        
        return {
            "title": f"Everything You Need to Know About {topic}",
            "description": f"Learn all about {topic} in this informative video. We cover the key facts and information you need to know.",
            "tags": [topic.lower().replace(" ", ""), "education", "facts", "information", "learn"],
            "segments": [
                {
                    "type": "intro",
                    "text": f"Welcome! Today we're exploring {topic}. This is a fascinating subject that everyone should know about.",
                    "duration": max(5, duration_seconds // 5),
                    "visual_suggestion": f"Title card showing {topic}"
                },
                {
                    "type": "content",
                    "text": f"{topic} is an interesting and important topic. It has many aspects worth learning about. [PAUSE] Understanding {topic} can help you in many ways.",
                    "duration": max(10, duration_seconds * 3 // 5),
                    "visual_suggestion": f"Illustration of {topic}"
                },
                {
                    "type": "outro",
                    "text": "Thanks for watching! If you enjoyed this video, please like and subscribe for more content. Leave a comment below with your thoughts!",
                    "duration": max(5, duration_seconds // 5),
                    "visual_suggestion": "Call to action screen"
                }
            ]
        }

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
