import subprocess
import os
from PIL import Image

def capture_image(image_path):
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        
        # Capture an image using libcamera-still
        subprocess.run(['libcamera-still', '-o', image_path], check=True)
        print(f"Image captured: {image_path}")
s        
        # Rotate the captured image using Pillow
        rotate_image(image_path)
        
    except Exception as e:
        print(f"Failed to capture image: {e}")

def rotate_image(image_path):
    with Image.open(image_path) as img:
        # Rotate 90 degress counterclockwise
        rotated_img = img.rotate(90, expand=True)
        
        # Save the rotated image back to the same path
        rotated_img.save(image_path)
        print(f"Image rotated: {image_path}")

if __name__ == "__main__":
    # Example usage
    capture_image('./captured_image.jpg')
