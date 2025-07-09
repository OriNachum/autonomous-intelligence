#!/usr/bin/env python3
"""
Script to download and cache the Gemma3n model before running the server.
This ensures the model is available and reduces startup time.
"""

import os
import sys
import torch
from transformers import AutoProcessor, Gemma3nForConditionalGeneration
from huggingface_hub import login


def download_model(model_id="google/gemma-3n-e4b"):
    """Download and cache the model."""
    print(f"Downloading model: {model_id}")
    print("-" * 50)
    
    # Check if HF token is needed
    hf_token = os.getenv("HUGGING_FACE_HUB_TOKEN", os.getenv("HF_TOKEN"))
    if hf_token:
        print("Logging in to Hugging Face Hub...")
        login(token=hf_token)
    
    # Determine device and dtype
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    
    print(f"Device: {device}")
    print(f"Dtype: {dtype}")
    print("-" * 50)
    
    try:
        # Download processor
        print("Downloading processor...")
        processor = AutoProcessor.from_pretrained(model_id)
        print("✓ Processor downloaded successfully")
        
        # Download model
        print("\nDownloading model weights...")
        print("This may take several minutes depending on your internet connection...")
        
        model = Gemma3nForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=dtype,
            low_cpu_mem_usage=True
        )
        
        print("✓ Model downloaded successfully")
        
        # Test model loading
        print("\nTesting model loading...")
        model = model.to(device)
        model.eval()
        
        # Simple test
        test_input = processor("Hello", return_tensors="pt").to(device)
        with torch.no_grad():
            _ = model.generate(**test_input, max_new_tokens=1)
        
        print("✓ Model test passed")
        print("\nModel is ready to use!")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error downloading model: {e}")
        print("\nTroubleshooting:")
        print("1. Check your internet connection")
        print("2. If the model is gated, ensure HF_TOKEN is set in your .env file")
        print("3. Verify the model ID is correct")
        print("4. Check available disk space")
        return False


if __name__ == "__main__":
    model_id = os.getenv("MODEL_NAME", "google/gemma-3n-e4b")
    
    print("Gemma3n Model Downloader")
    print("=" * 50)
    
    success = download_model(model_id)
    
    if not success:
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("Download complete! You can now run the API server.")