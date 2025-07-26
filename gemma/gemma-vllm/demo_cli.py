#!/usr/bin/env python3
"""
Gemma 3n vLLM Demo CLI
Simple command-line interface for testing Gemma 3n multimodal capabilities
"""

import argparse
import base64
import json
import os
import sys
from typing import List, Dict, Any
import requests
from PIL import Image
import io

VLLM_URL = os.getenv("VLLM_URL", "http://localhost:8000")
MODEL_NAME = os.getenv("MODEL_NAME", "gemma3n")


def encode_image(image_path: str) -> str:
    """Encode image to base64 string."""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize if too large (max 1024x1024)
            if img.width > 1024 or img.height > 1024:
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            img_data = buffer.getvalue()
            return base64.b64encode(img_data).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        sys.exit(1)


def encode_audio(audio_path: str) -> str:
    """Encode audio file to base64 string."""
    try:
        with open(audio_path, 'rb') as audio_file:
            audio_data = audio_file.read()
            return base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        print(f"Error encoding audio {audio_path}: {e}")
        sys.exit(1)


def create_message_content(text: str, images: List[str] = None, audio: str = None) -> List[Dict[str, Any]]:
    """Create message content array for multimodal input."""
    content = []
    
    # Add text content
    if text:
        content.append({"type": "text", "text": text})
    
    # Add image content
    if images:
        for img_path in images:
            img_b64 = encode_image(img_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })
    
    # Add audio content (if supported by vLLM)
    if audio:
        audio_b64 = encode_audio(audio)
        content.append({
            "type": "audio",
            "audio": {"data": audio_b64, "format": "auto"}
        })
    
    return content


def call_vllm_api(messages: List[Dict[str, Any]]) -> str:
    """Call vLLM OpenAI-compatible API."""
    url = f"{VLLM_URL}/v1/chat/completions"
    
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
        "stream": False
    }
    
    try:
        print(f"Calling vLLM API at {url}...")
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to vLLM server at {VLLM_URL}")
        print("Make sure the vLLM server is running with: docker compose up vllm")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Error: Request timed out. The model might be processing a large input.")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        if response.text:
            print(f"Response: {response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Gemma 3n vLLM Demo CLI - Test multimodal capabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Text only
  python demo_cli.py --text "Hello, how are you?"
  
  # Text + Image
  python demo_cli.py --text "What do you see in this image?" --image photo.jpg
  
  # Text + Multiple Images
  python demo_cli.py --text "Compare these images" --image img1.jpg --image img2.jpg
  
  # Text + Audio (if supported)
  python demo_cli.py --text "Transcribe this audio" --audio recording.wav
  
  # All modalities
  python demo_cli.py --text "Analyze this content" --image photo.jpg --audio audio.wav
        """
    )
    
    parser.add_argument("--text", "-t", type=str, help="Text input")
    parser.add_argument("--image", "-i", action="append", help="Image file path (can be used multiple times)")
    parser.add_argument("--audio", "-a", type=str, help="Audio file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Validate inputs
    if not any([args.text, args.image, args.audio]):
        print("Error: At least one input type (text, image, or audio) must be provided.")
        parser.print_help()
        sys.exit(1)
    
    # Check if files exist
    if args.image:
        for img_path in args.image:
            if not os.path.exists(img_path):
                print(f"Error: Image file not found: {img_path}")
                sys.exit(1)
    
    if args.audio and not os.path.exists(args.audio):
        print(f"Error: Audio file not found: {args.audio}")
        sys.exit(1)
    
    # Create message content
    content = create_message_content(
        text=args.text or "Please analyze the provided content.",
        images=args.image,
        audio=args.audio
    )
    
    messages = [{"role": "user", "content": content}]
    
    if args.verbose:
        print(f"Sending request to vLLM...")
        print(f"Text: {args.text}")
        if args.image:
            print(f"Images: {args.image}")
        if args.audio:
            print(f"Audio: {args.audio}")
        print("-" * 50)
    
    # Call the API
    response = call_vllm_api(messages)
    
    # Output the response
    print("Response:")
    print(response)


if __name__ == "__main__":
    main()