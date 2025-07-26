#!/usr/bin/env python3
"""
Download Gemma 3n model for vLLM
"""

import os
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

# Model configurations
MODELS = {
    "full": {
        "repo_id": "google/gemma-3n-E4B",
        "local_dir": "./models/gemma3n-full",
        "description": "Full precision Gemma 3n-E4B model"
    },
    "fp16": {
        "repo_id": "muranAI/gemma-3n-e4b-it-fp16", 
        "local_dir": "./models/gemma3n",
        "description": "FP16 quantized Gemma 3n-E4B model (recommended for Jetson)"
    }
}

def check_hf_token():
    """Check if HuggingFace token is available."""
    token = os.getenv("HF_TOKEN")
    if not token:
        print("Error: HF_TOKEN environment variable not set.")
        print("Please set your HuggingFace token in the .env file:")
        print("  echo 'HF_TOKEN=your_token_here' >> .env")
        sys.exit(1)
    return token

def download_model(model_key: str = "fp16"):
    """Download the specified model."""
    if model_key not in MODELS:
        print(f"Error: Unknown model '{model_key}'. Available models: {list(MODELS.keys())}")
        sys.exit(1)
    
    model_config = MODELS[model_key]
    
    print(f"Downloading {model_config['description']}...")
    print(f"Repository: {model_config['repo_id']}")
    print(f"Local directory: {model_config['local_dir']}")
    
    # Create models directory
    Path(model_config['local_dir']).mkdir(parents=True, exist_ok=True)
    
    # Check if model already exists
    model_path = Path(model_config['local_dir'])
    if model_path.exists() and any(model_path.iterdir()):
        print(f"Model already exists in {model_config['local_dir']}")
        response = input("Do you want to re-download? (y/N): ")
        if response.lower() != 'y':
            print("Skipping download.")
            return
    
    # Download model
    try:
        token = check_hf_token()
        
        snapshot_download(
            repo_id=model_config['repo_id'],
            local_dir=model_config['local_dir'],
            token=token,
            resume_download=True,
            local_dir_use_symlinks=False
        )
        
        print(f"Successfully downloaded model to {model_config['local_dir']}")
        
    except Exception as e:
        print(f"Error downloading model: {e}")
        sys.exit(1)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Download Gemma 3n model for vLLM")
    parser.add_argument(
        "--model", 
        choices=list(MODELS.keys()), 
        default="fp16",
        help="Model variant to download (default: fp16)"
    )
    parser.add_argument(
        "--list", 
        action="store_true",
        help="List available models"
    )
    
    args = parser.parse_args()
    
    if args.list:
        print("Available models:")
        for key, config in MODELS.items():
            print(f"  {key}: {config['description']}")
            print(f"    Repository: {config['repo_id']}")
            print(f"    Local path: {config['local_dir']}")
            print()
        return
    
    download_model(args.model)

if __name__ == "__main__":
    main()