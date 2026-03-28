"""LLM provider implementations for free model access."""

import os
import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMResponse:
    """Standard response format from any LLM provider."""
    content: str
    raw_response: Optional[Dict] = None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, 
                 json_mode: bool = False) -> LLMResponse:
        """Generate text completion."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and reachable."""
        pass


class OllamaProvider(BaseLLMProvider):
    """Local LLM via Ollama API."""
    
    def __init__(self, model: Optional[str] = None, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        # Auto-detect model if not specified
        self.model = model or self._auto_detect_model()
    
    def _auto_detect_model(self) -> str:
        """Auto-detect available model from Ollama and show all models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                if models:
                    # Print all available models
                    print("\nAvailable Ollama models:")
                    model_names = []
                    for m in models:
                        name = m.get("name", m.get("model", "unknown"))
                        model_names.append(name)
                        print(f"  - {name}")
                    
                    # Prefer common models
                    preferred = ["qwen3.5", "qwen2.5", "llama3.2", "llama3.1", "mistral", "phi3"]
                    for model_name in preferred:
                        for name in model_names:
                            if model_name in name.lower():
                                print(f"\nSelected: {name}")
                                return name
                    
                    # Fallback to first available
                    print(f"\nSelected: {model_names[0]}")
                    return model_names[0]
        except Exception as e:
            print(f"Model detection failed: {e}")
        return "llama3.2"
    
    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        url = f"{self.base_url}/api/generate"
        
        full_prompt = prompt
        if json_mode:
            full_prompt += "\n\nIMPORTANT: Respond with valid JSON only. No markdown, no explanations."
        if system_prompt:
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.7}
        }
        
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        
        content = data.get("response", "").strip()
        
        if json_mode:
            content = self._extract_json(content)
        
        return LLMResponse(content=content, raw_response=data)
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text response."""
        # Try to find JSON block
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'(\{.*\})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()
        return text


class GroqProvider(BaseLLMProvider):
    """Groq API for fast inference."""
    
    MODELS = {
        "llama-3.3-70b": "llama-3.3-70b-versatile",
        "mixtral": "mixtral-8x7b-32768",
        "gemma": "gemma2-9b-it",
        "llama-3.1-8b": "llama-3.1-8b-instant"
    }
    
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = self.MODELS.get(model, model)
        self.base_url = "https://api.groq.com/openai/v1"
    
    def is_available(self) -> bool:
        return self.api_key is not None and len(self.api_key) > 10
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4000
        }
        
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(content=content, raw_response=data)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API."""
    
    MODELS = {
        "flash": "gemini-1.5-flash",
        "flash-8b": "gemini-1.5-flash-8b",
        "pro": "gemini-1.5-pro"
    }
    
    def __init__(self, api_key: Optional[str] = None, model: str = "flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = self.MODELS.get(model, model)
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    def is_available(self) -> bool:
        return self.api_key is not None and len(self.api_key) > 10
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        url = f"{self.base_url}/models/{self.model}:generateContent"
        
        full_prompt = prompt
        if json_mode:
            full_prompt += "\n\nIMPORTANT: Respond with valid JSON only. No markdown formatting."
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{full_prompt}"
        
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4000
            }
        }
        
        response = requests.post(
            f"{url}?key={self.api_key}",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        
        if json_mode:
            content = self._extract_json(content)
        
        return LLMResponse(content=content, raw_response=data)
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from markdown code blocks if present."""
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()


class LLMProviderFactory:
    """Factory to create LLM providers with fallback."""
    
    PROVIDERS = {
        "ollama": OllamaProvider,
        "groq": GroqProvider,
        "gemini": GeminiProvider
    }
    
    @classmethod
    def create(cls, provider_name: Optional[str] = None, **kwargs) -> BaseLLMProvider:
        """Create a provider by name or auto-detect."""
        provider_name = provider_name or os.getenv("CONTENT_PROVIDER", "auto")
        
        if provider_name == "auto":
            return cls._auto_detect(**kwargs)
        
        provider_class = cls.PROVIDERS.get(provider_name)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        return provider_class(**kwargs)
    
    @classmethod
    def _auto_detect(cls, **kwargs) -> BaseLLMProvider:
        """Auto-detect available provider in priority order."""
        # Priority: Ollama (local) -> Groq -> Gemini
        providers = [
            ("ollama", OllamaProvider),
            ("groq", GroqProvider),
            ("gemini", GeminiProvider)
        ]
        
        for name, provider_class in providers:
            try:
                provider = provider_class(**kwargs)
                if provider.is_available():
                    print(f"Auto-selected provider: {name}")
                    return provider
            except Exception as e:
                print(f"Provider {name} not available: {e}")
                continue
        
        raise RuntimeError("No LLM provider available. Please configure Ollama, GROQ_API_KEY, or GEMINI_API_KEY")
    
    @classmethod
    def list_available(cls) -> list:
        """List available providers."""
        available = []
        for name, provider_class in cls.PROVIDERS.items():
            try:
                provider = provider_class()
                if provider.is_available():
                    available.append(name)
            except:
                pass
        return available


if __name__ == "__main__":
    # Test providers
    print("Available providers:", LLMProviderFactory.list_available())
    
    # Quick test
    try:
        provider = LLMProviderFactory.create()
        response = provider.generate("Say 'Hello from free models' in one sentence.")
        print(f"\nResponse: {response.content}")
    except Exception as e:
        print(f"Error: {e}")
