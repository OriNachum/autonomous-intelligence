#!/usr/bin/env python3

import os
import sys
from pathlib import Path

def download_gemma3n_model():
    """Download Gemma 3n model for SGLang."""
    
    model_dir = Path("./models/gemma3n")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    # Model identifier - adjust based on actual Gemma 3n model path
    model_id = os.getenv("MODEL_ID", "google/gemma-3n-e4b")
    hf_token = os.getenv("HF_TOKEN")
    
    if not hf_token:
        print("Warning: HF_TOKEN not set. You may need authentication for private models.")
    
    print(f"Downloading model: {model_id}")
    print(f"Target directory: {model_dir.absolute()}")
    
    try:
        from huggingface_hub import snapshot_download
        
        # Download model
        snapshot_download(
            repo_id=model_id,
            local_dir=str(model_dir),
            token=hf_token,
            resume_download=True,
            local_dir_use_symlinks=False
        )
        
        print(f"Model downloaded successfully to {model_dir}")
        
    except ImportError:
        print("huggingface_hub not installed. Installing...")
        os.system("pip install huggingface_hub")
        
        # Retry download
        from huggingface_hub import snapshot_download
        
        snapshot_download(
            repo_id=model_id,
            local_dir=str(model_dir),
            token=hf_token,
            resume_download=True,
            local_dir_use_symlinks=False
        )
        
        print(f"Model downloaded successfully to {model_dir}")
        
    except Exception as e:
        print(f"Error downloading model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    download_gemma3n_model()