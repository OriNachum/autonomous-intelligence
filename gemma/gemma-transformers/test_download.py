#!/usr/bin/env python3
"""Test script to verify model download and basic functionality."""

import os
import sys
from transformers import AutoProcessor, AutoModelForVision2Seq, AutoConfig
from huggingface_hub import login
import torch

def test_model_download():
    model_id = os.getenv("MODEL_NAME", "google/gemma-3n-e4b")
    cache_dir = os.getenv("HF_HOME", "/cache/huggingface")
    
    print(f"Testing model: {model_id}")
    print(f"Cache directory: {cache_dir}")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    
    # Check if HF token is set
    hf_token = os.getenv("HUGGING_FACE_HUB_TOKEN", os.getenv("HF_TOKEN"))
    if hf_token:
        print("HF token found, logging in...")
        try:
            login(token=hf_token)
            print("✓ Successfully logged in to Hugging Face")
        except Exception as e:
            print(f"✗ Failed to login: {e}")
            return False
    
    try:
        # First, try to get the config to check model availability
        print("\nChecking model availability...")
        config = AutoConfig.from_pretrained(model_id, cache_dir=cache_dir)
        print(f"✓ Model config loaded: {config.model_type}")
        
        # Try to load processor
        print("\nLoading processor...")
        processor = AutoProcessor.from_pretrained(model_id, cache_dir=cache_dir)
        print("✓ Processor loaded successfully")
        
        # Try to load model
        print("\nLoading model (this may take a while)...")
        model = AutoModelForVision2Seq.from_pretrained(
            model_id,
            cache_dir=cache_dir,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            low_cpu_mem_usage=True
        )
        print("✓ Model loaded successfully")
        print(f"Model type: {type(model).__name__}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nPossible issues:")
        print("1. Model name might be incorrect")
        print("2. Model might require authentication (check HF_TOKEN)")
        print("3. Network connection issues")
        print("4. Insufficient disk space")
        return False

if __name__ == "__main__":
    success = test_model_download()
    sys.exit(0 if success else 1)