#!/usr/bin/env python3
"""
Script to download processor models (specifically YOLO) to a local directory.
This allows models to be cached and available without runtime downloads.
"""

import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("download_models")

def download_yolo_model(model_name: str, output_dir: Path):
    """
    Download YOLO model using ultralytics.
    """
    try:
        from ultralytics import YOLO
        
        logger.info(f"Checking/Downloading YOLO model: {model_name} to {output_dir}")
        
        # We can't easily tell ultralytics WHERE to download the file directly via the constructor 
        # without it loading it. However, if we load it, it downloads to current dir or settings dir.
        # A better approach for "download only" is to let YOLO handle it, but we want to ensure 
        # it ends up in our target directory.
        
        # Ultralytics checks the current directory first.
        # So if we change cwd to output_dir, it should download there.
        
        original_cwd = os.getcwd()
        try:
            os.chdir(output_dir)
            # Just initializing the class triggers download if not present
            model = YOLO(model_name)
            logger.info(f"Model {model_name} is ready at {output_dir / model_name}")
        finally:
            os.chdir(original_cwd)
            
        return True
        
    except ImportError:
        logger.error("ultralytics package not installed. Run: pip install ultralytics")
        return False
    except Exception as e:
        logger.error(f"Failed to download YOLO model: {e}", exc_info=True)
        return False

def main():
    # Get models directory from env or default
    models_dir = os.environ.get("PROCESSOR_MODELS_DIR", "/data/models/processors")
    models_path = Path(models_dir)
    
    # Create directory if it doesn't exist
    if not models_path.exists():
        logger.info(f"Creating models directory: {models_path}")
        models_path.mkdir(parents=True, exist_ok=True)
    
    # Download YOLOv8 Nano
    download_yolo_model("yolov8n.pt", models_path)
    
    # Add other models here if needed in the future

if __name__ == "__main__":
    main()
