#!/usr/bin/env python3
"""Example usage of the YouTube content creation pipeline."""

import asyncio
from pipeline import YouTubePipeline


async def example_single_video():
    """Create a single video."""
    pipeline = YouTubePipeline()
    
    result = await pipeline.create_video(
        topic="5 Fascinating Facts About Black Holes",
        duration=45,
        style="educational",
        upload=False  # Set to True to upload
    )
    
    print(f"Created: {result['title']}")
    print(f"Video: {result['video_path']}")


async def example_batch_videos():
    """Create multiple videos from topics list."""
    topics = [
        "How do vaccines work",
        "The history of the Internet",
        "What is blockchain technology"
    ]
    
    pipeline = YouTubePipeline()
    
    for topic in topics:
        print(f"\n--- Processing: {topic} ---")
        result = await pipeline.create_video(
            topic=topic,
            duration=60,
            style="educational",
            upload=False
        )
        print(f"Done: {result['video_path']}")


def example_direct_import():
    """Use individual modules directly."""
    from content_generator import ContentGenerator
    from media_generator import MediaGenerator
    
    # Generate content only
    gen = ContentGenerator()
    content = gen.generate_script("The benefits of meditation", duration=30)
    
    print(f"Title: {content['title']}")
    print(f"Description: {content['description'][:100]}...")
    
    # Generate audio only
    media = MediaGenerator()
    
    async def get_audio():
        path = await media.generate_speech(content['segments'][0]['text'])
        print(f"Audio: {path}")
    
    asyncio.run(get_audio())


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "single":
            asyncio.run(example_single_video())
        elif sys.argv[1] == "batch":
            asyncio.run(example_batch_videos())
        elif sys.argv[1] == "modules":
            example_direct_import()
        else:
            print("Usage: python example_usage.py [single|batch|modules]")
    else:
        print("YouTube Pipeline Examples")
        print("-" * 40)
        print("Run with argument:")
        print("  python example_usage.py single  - Create one video")
        print("  python example_usage.py batch   - Create multiple videos")
        print("  python example_usage.py modules - Test individual modules")
