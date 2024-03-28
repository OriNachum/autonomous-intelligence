from picamera import Picamera2, OptionsUnbounded
import time

class CameraService:
    def __init__(self):
        self.camera = Picamera2()
        self.camera.start()
        self.configure = self.camera.create_configuration(OptionsUnbounded())
        self.configure["rotation"] = -90

    def capture_image(self, filename):
        metadata = self.camera.capture_request()
        self.camera.capture(metadata, filename, bayer=True)

if __name__ == "__main__":
    camera_service = CameraService()

    print("Camera service started. Press Ctrl+C to exit.")
    try:
        counter = 1
        while True:
            filename = f"image_{counter}.jpg"
            print(f"Capturing {filename}...")
            camera_service.capture_image(filename)
            counter += 1
            time.sleep(5)  # Adjust delay between captures as needed
    except KeyboardInterrupt:
        print("Stopping camera service...")
    finally:
        camera_service.camera.stop()
        print("Camera service stopped.")
