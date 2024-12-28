import requests

class FaceDetector:
    def __init__(self, vision_server_ip_location="./batch/output/nmap_output.txt"):
        self.vision_server_ip_location = vision_server_ip_location
        self.base_ip = self.locate_server()

    def locate_server(self):
        # Open the file in read mode
        with open(self.vision_server_ip_location, 'r') as file:
            # Read the first line
            first_line = file.readline()
            first_line = first_line if first_line != "" else '192.168.1.101'
            first_line = first_line.replace('%0a', '').replace('\n', "")
        return first_line

    def detect_faces(self, image_path):
        # Construct the URL for the FastAPI server
        url = f"http://{self.base_ip}:8000/detect_faces"
        print(url)

        # Set the headers
        headers = {
            'accept': 'application/json',
            # 'Content-Type': 'multipart/form-data',
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
            
if __name__ == "__main__":
    # Test the FaceDetector class
    fd = FaceDetector()
    result = fd.detect_faces("path/to/image.jpg")
    if result:
        print("Face detection successful!")
    else:
        print("Face detection failed.")
