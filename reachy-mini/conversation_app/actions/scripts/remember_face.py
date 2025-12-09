#!/usr/bin/env python3
import sys
import os
import shutil
import logging
from pathlib import Path

# Add parent directory to path to import gateway
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger("name_face")
    
async def execute(gateway, tts_queue, params):
    """
    Rename a face directory and reload vision models.
    
    Args:
        gateway: ReachyGateway instance for robot control
        tts_queue: TTS queue for speech synthesis
        params: Dictionary with face parameters
    """
    faces_dir = Path("./conversation_app/data/faces")
    
    # Sanitize names (basic check)
    current_name = "".join(c for c in params.get('current_name', '') if c.isalnum() or c in ('-', '_'))
    new_name = "".join(c for c in params.get('new_name', '') if c.isalnum() or c in ('-', '_'))
    
    current_path = faces_dir / current_name
    new_path = faces_dir / new_name
    
    if not current_path.exists():
        error_msg = f"Face '{current_name}' not found."
        logger.error(error_msg)
        return {"success": False, "message": error_msg, "error": "not_found"}
    
    if new_path.exists():
        # Merge strategy: move all images from current to new directory
        try:
            logger.info(f"Face '{new_name}' already exists, merging...")
            for image_file in current_path.glob('*'):
                if image_file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                    # Find next available number for the file
                    base_name = new_name
                    counter = 1
                    while (new_path / f"{base_name}_{counter}.jpg").exists():
                        counter += 1
                    shutil.move(str(image_file), str(new_path / f"{base_name}_{counter}.jpg"))
            
            # Remove empty directory
            current_path.rmdir()
            logger.info(f"Merged '{current_name}' into '{new_name}'")
            message = f"Merged '{current_name}' into existing '{new_name}'."
        except Exception as e:
            error_msg = f"Error merging faces: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "error": "merge_failed"}
    else:
        try:
            # Rename directory
            shutil.move(str(current_path), str(new_path))
            logger.info(f"Renamed face '{current_name}' to '{new_name}'")
            message = f"Successfully renamed '{current_name}' to '{new_name}'."
        except Exception as e:
            error_msg = f"Failed to rename face: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "error": "rename_failed"}
    
    # Reload models if gateway is available
    if gateway:
        try:
            logger.info("Triggering vision model reload...")
            gateway.reload_vision_models()
            message += " Vision models reloaded."
        except Exception as e:
            logger.error(f"Failed to reload vision models: {e}")
            message += f" Warning: Vision reload failed - {str(e)}"
    else:
        logger.warning("No gateway provided, skipping vision model reload")
        message += " Note: Vision models not reloaded (no gateway)."
    
    return {"success": True, "message": message}

if __name__ == "__main__":
    # This script is usually imported and run by ActionHandler, 
    # but can be run standalone for testing if gateway is mocked or not needed for file ops
    if len(sys.argv) < 3:
        print("Usage: name_face.py <current_name> <new_name>")
        sys.exit(1)
        
    result = name_face(sys.argv[1], sys.argv[2])
    print(result.get('message', str(result)))
