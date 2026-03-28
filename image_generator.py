"""AI Image generation module using free models and APIs."""

import os
import time
import base64
import requests
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass
import random


@dataclass
class ImageConfig:
    """Configuration for image generation."""
    width: int = 1024
    height: int = 1024
    seed: Optional[int] = None
    negative_prompt: str = "blurry, low quality, distorted, ugly, deformed"


class FreeImageGenerator:
    """Generate images using free AI models and APIs."""
    
    def __init__(self, output_dir: str = "temp/images"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(output_dir) / "temp"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Available providers
        self.providers = {
            "pollinations": self._generate_pollinations,  # Completely free, no API key
            "huggingface": self._generate_hf,             # Free tier
            "clipdrop": self._generate_clipdrop,          # Free tier (Stability AI)
            "local": self._generate_local                 # Local Stable Diffusion
        }
    
    def generate_image(self, prompt: str, 
                       config: Optional[ImageConfig] = None,
                       output_path: Optional[str] = None,
                       provider: str = "pollinations") -> str:
        """
        Generate image using free AI model.
        
        Args:
            prompt: Image description
            config: Image generation config
            output_path: Output file path
            provider: Which provider to use
        """
        config = config or ImageConfig()
        
        if output_path is None:
            safe_prompt = "".join(c if c.isalnum() else "_" for c in prompt[:30])
            output_path = self.output_dir / f"img_{safe_prompt}_{int(time.time())}.png"
        else:
            output_path = Path(output_path)
        
        # Get generator function
        generator = self.providers.get(provider)
        if not generator:
            raise ValueError(f"Unknown provider: {provider}")
        
        try:
            return generator(prompt, config, str(output_path))
        except Exception as e:
            print(f"Provider {provider} failed: {e}")
            # Try fallback providers
            for fallback in ["huggingface", "pollinations"]:
                if fallback != provider:
                    try:
                        print(f"Trying fallback: {fallback}")
                        return self.providers[fallback](prompt, config, str(output_path))
                    except:
                        continue
            raise RuntimeError("All image providers failed")
    
    def _generate_pollinations(self, prompt: str, config: ImageConfig, output_path: str) -> str:
        """Generate using Pollinations AI (completely free, no API key needed)."""
        # Pollinations is an open, free image generation service
        encoded_prompt = requests.utils.quote(prompt)
        
        # Add seed for reproducibility
        seed = config.seed or random.randint(1, 1000000)
        
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={config.width}&height={config.height}&seed={seed}&nologo=true"
        
        print(f"Generating image via Pollinations...")
        
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        
        with open(output_path, "wb") as f:
            f.write(response.content)
        
        return output_path
    
    def _generate_hf(self, prompt: str, config: ImageConfig, output_path: str) -> str:
        """Generate using Hugging Face Inference API (free tier)."""
        # Using Stable Diffusion via Hugging Face
        api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"
        
        headers = {}
        hf_token = os.getenv("HF_API_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": config.negative_prompt,
                "width": min(config.width, 512),  # HF limit
                "height": min(config.height, 512),
                "seed": config.seed or random.randint(1, 1000000)
            }
        }
        
        print(f"Generating image via HuggingFace...")
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        
        if response.status_code == 200:
            image_bytes = response.content
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            return output_path
        else:
            raise Exception(f"HF API error: {response.status_code}")
    
    def _generate_clipdrop(self, prompt: str, config: ImageConfig, output_path: str) -> str:
        """Generate using Clipdrop (Stability AI free tier)."""
        api_key = os.getenv("CLIPDROP_API_KEY")
        if not api_key:
            raise ValueError("CLIPDROP_API_KEY not set")
        
        url = "https://clipdrop-api.co/text-to-image/v1"
        
        headers = {"x-api-key": api_key}
        
        files = {
            "prompt": (None, prompt),
        }
        
        response = requests.post(url, headers=headers, files=files, timeout=120)
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
        else:
            raise Exception(f"Clipdrop error: {response.status_code}")
    
    def _generate_local(self, prompt: str, config: ImageConfig, output_path: str) -> str:
        """Generate using local Stable Diffusion via diffusers."""
        try:
            import torch
            from diffusers import StableDiffusionPipeline
            
            print("Loading Stable Diffusion model...")
            
            # Use a lightweight model
            model_id = "runwayml/stable-diffusion-v1-5"
            
            pipe = StableDiffusionPipeline.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                safety_checker=None,
                requires_safety_checker=False
            )
            
            if torch.cuda.is_available():
                pipe = pipe.to("cuda")
            
            # Generate
            generator = torch.Generator()
            if config.seed:
                generator = generator.manual_seed(config.seed)
            
            image = pipe(
                prompt,
                negative_prompt=config.negative_prompt,
                width=config.width,
                height=config.height,
                num_inference_steps=25,
                generator=generator
            ).images[0]
            
            image.save(output_path)
            return output_path
            
        except ImportError:
            raise ImportError("diffusers and torch required. Run: pip install diffusers torch")
    
    def generate_images_for_script(self, segments: List[Dict], 
                                   output_dir: Optional[str] = None) -> List[str]:
        """Generate images for each video segment based on visual suggestions."""
        if output_dir:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
        else:
            out_path = self.output_dir
        
        image_paths = []
        
        for i, segment in enumerate(segments):
            # Get visual suggestion from segment
            visual = segment.get("visual_suggestion", "")
            seg_type = segment.get("type", "content")
            
            if not visual:
                # Generate a generic prompt based on segment type
                if seg_type == "intro":
                    visual = f"abstract cinematic opening scene, {segment.get('title', 'title')}"
                elif seg_type == "outro":
                    visual = "abstract ending scene, thank you screen, professional"
                else:
                    visual = f"illustration of: {segment.get('text', '')[:50]}"
            
            # Enhance prompt for better results
            enhanced_prompt = self._enhance_prompt(visual, seg_type)
            
            try:
                output_path = out_path / f"segment_{i:03d}.png"
                img_path = self.generate_image(
                    prompt=enhanced_prompt,
                    output_path=str(output_path),
                    provider="pollinations"  # Default to free option
                )
                image_paths.append(img_path)
                print(f"  Generated image for segment {i}: {img_path}")
            except Exception as e:
                print(f"  Failed to generate image for segment {i}: {e}")
                image_paths.append(None)
        
        return image_paths
    
    def _enhance_prompt(self, base_prompt: str, seg_type: str) -> str:
        """Enhance prompt for better AI image generation results."""
        # Add style modifiers based on segment type
        style_modifiers = {
            "intro": "cinematic, epic, high quality, dramatic lighting, 4k",
            "outro": "professional, clean, simple background, text space",
            "content": "illustration, detailed, colorful, high quality, digital art"
        }
        
        modifier = style_modifiers.get(seg_type, "high quality, detailed, professional")
        
        # Combine
        enhanced = f"{base_prompt}, {modifier}"
        return enhanced
    
    def create_thumbnail_image(self, title: str, output_path: Optional[str] = None) -> str:
        """Create thumbnail image for video."""
        if output_path is None:
            output_path = self.output_dir / f"thumb_{int(time.time())}.png"
        
        prompt = f"YouTube thumbnail, {title}, eye-catching, bold colors, professional, high contrast"
        
        return self.generate_image(
            prompt=prompt,
            output_path=str(output_path),
            config=ImageConfig(width=1280, height=720)
        )


class ImageLibrary:
    """Simple image library for fallback when AI generation fails."""
    
    def __init__(self, library_dir: str = "assets/images"):
        self.library_dir = Path(library_dir)
        self.library_dir.mkdir(parents=True, exist_ok=True)
    
    def search_stock_images(self, query: str, count: int = 5) -> List[str]:
        """Search free stock image sources."""
        # Return URLs from Unsplash
        urls = []
        for _ in range(count):
            # Unsplash source redirects to random matching image
            url = f"https://source.unsplash.com/1024x1024/?{requests.utils.quote(query)}"
            urls.append(url)
        return urls
    
    def download_image(self, url: str, output_path: str) -> str:
        """Download image from URL."""
        response = requests.get(url, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        with open(output_path, "wb") as f:
            f.write(response.content)
        
        return output_path


if __name__ == "__main__":
    # Test image generation
    gen = FreeImageGenerator()
    
    print("Testing free image generation...")
    
    try:
        # Test with Pollinations (no API key needed)
        img_path = gen.generate_image(
            prompt="A futuristic city at sunset, cyberpunk style",
            provider="pollinations"
        )
        print(f"Generated: {img_path}")
        
        # Test thumbnail
        thumb = gen.create_thumbnail_image("Amazing Space Facts")
        print(f"Thumbnail: {thumb}")
        
    except Exception as e:
        print(f"Error: {e}")
