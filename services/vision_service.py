import requests


vision_server_ip_location="./batch/output/nmap_output.txt"

def _get_faces_url(base_ip, image_path):

    # Construct the URL for the FastAPI server
    url = f"http://{base_ip}:8000/process_image"
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

if __name__ == "__main__":
    #vision_server_ip_location = "./batch/output/nmap_output.txt"
    # Open the file in read mode
    with open(vision_server_ip_location, 'r') as file:
    # Read the first line
        first_line = file.readline()
    first_line='192.168.1.101'
    image_path = "image.jpg"  # Change this to the path of your image file
    faces_data = _get_faces_url(first_line, image_path)
    with open('faces.zip', "wb") as zip:
        zip.write(faces_data)
																		
