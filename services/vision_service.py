import requests
import zipfile
from io import BytesIO
import os


vision_server_ip_location="./batch/output/nmap_output.txt"

# movie to client, add remember and forget faces
def _detect_faces(base_ip, image_path):

    # Construct the URL for the FastAPI server
    url = f"http://{base_ip}:8000/detect_faces"
    print(url)

    # Set the headers
    headers = {
        'accept': 'application/json',
#        'Content-Type': 'multipart/form-data',
    }
    
    # Prepare the files data
    with open(image_path, 'rb') as file:
        files = {
           'file': (image_path, file, 'multipart/form-data')
        }

        # Make the POST request
        with requests.Session() as s:
            response = s.post(url, headers=headers, files=files)
            print(response.status_code)
    
    # Check if the request was successful
    if response.status_code == 200:
        # Return the JSON response
        return response.content
    else:
        # Print error message if request failed
        print(f"Error: {response.status_code} - {response.text}")
        return None

# add remember by name. and forget faces by name. always detect first!
def detect_faces(image_path):
    #vision_server_ip_location = "./batch/output/nmap_output.txt"
    # Open the file in read mode
    with open(vision_server_ip_location, 'r') as file:
    # Read the first line
        first_line = file.readline()
    first_line= first_line if first_line != "" else '192.168.1.101'
    first_line=first_line.replace('%0a', '').replace('\n',"")
    faces_data = _detect_faces(first_line, image_path)
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
