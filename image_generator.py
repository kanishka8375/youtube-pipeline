"""Simple image generation using Pollinations AI (free, no API key)."""

import time
import random
import requests
from pathlib import Path
from typing import Optional, List, Dict


def _download_with_retry(url: str, max_retries: int = 3, timeout: int = 120) -> Optional[bytes]:
    """Download with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.exceptions.Timeout:
            wait_time = 2 ** attempt  # 1, 2, 4 seconds
            print(f"  Image download timeout (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
            time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"  Image download error: {e}, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
    return None


class FreeImageGenerator:
    """Generate images using Pollinations AI (free, reliable)."""
    
    def __init__(self, output_dir: str = "temp/images"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_image(self, prompt: str, output_path: Optional[str] = None) -> Optional[str]:
        """Generate image using Pollinations AI."""
        if output_path is None:
            safe_prompt = "".join(c if c.isalnum() else "_" for c in prompt[:30])
            output_path = self.output_dir / f"img_{safe_prompt}_{int(time.time())}.png"
        else:
            output_path = Path(output_path)
        
        try:
            encoded_prompt = requests.utils.quote(prompt)
            seed = random.randint(1, 1000000)
            
            # Pollinations is free and reliable
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true"
            
            image_data = _download_with_retry(url, max_retries=3, timeout=120)
            if image_data is None:
                return None
            
            with open(output_path, "wb") as f:
                f.write(image_data)
            
            return str(output_path)
            
        except Exception as e:
            print(f"Image generation failed: {e}")
            return None
    
    def generate_images_for_script(self, segments: List[Dict]) -> List[Optional[str]]:
        """Generate images for each content segment."""
        image_paths = []
        
        for i, segment in enumerate(segments):
            seg_type = segment.get("type", "content")
            
            if seg_type != "content":
                image_paths.append(None)
                continue
            
            visual = segment.get("visual_suggestion", "")
            text = segment.get("text", "")
            
            # Enhance prompt
            prompt = visual or text[:100]
            prompt = f"{prompt}, high quality, detailed, illustration"
            
            output_path = self.output_dir / f"segment_{i:03d}.png"
            img_path = self.generate_image(prompt, str(output_path))
            
            if img_path:
                print(f"  Scene {i}: Image generated")
            else:
                print(f"  Scene {i}: No image (continuing)")
            
            image_paths.append(img_path)
        
        return image_paths


if __name__ == "__main__":
    gen = FreeImageGenerator()
    img = gen.generate_image("A futuristic city at sunset")
    print(f"Generated: {img}")
