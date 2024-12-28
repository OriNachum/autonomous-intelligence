import base64

def take_a_picture(image_path):
        capture_image(image_path)
        with open(image_path, "rb") as file:
            image_bytes = file.read()
            image_encoded = base64.b64encode(image_bytes).decode("utf-8")
            request = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_encoded
                    }
                },
                {
                    "type": "text",
                    "text": "Here is the photo you have taken. What you see in the image is what's in front of you. This is what you see from your Raspberry Pi body and camera module."
                }
            ]
            return request
