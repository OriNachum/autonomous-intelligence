import requests
import zipfile
from io import BytesIO
import os
import sys

if __name__ == "__main__":
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)

from clients.face_detector import FaceDetector

vision_server_ip_location="./batch/output/nmap_output.txt"

# add remember by name. and forget faces by name. always detect first!
def detect_faces(image_path):
    face_detector = FaceDetector()
    faces_data = face_detector.detect_faces(image_path)
    zip_buffer = BytesIO(faces_data)
    
    target_dir="temp_detected_faces"
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
    # Extract all files from the ZIP file
        zip_file.extractall(path=target_dir)
    
        # Iterate over the extracted files and print the filenames
        return zip_file.namelist()
                                                                            
if __name__ == "__main__":
    image_path = "image.jpg"  # Change this to the path of your image file
    face_names = detect_faces(image_path)
    print(f"Faces found:\n{face_names}")
