import hailo_sdk as hailo
import numpy as np
import cv2

class FaceDetectionHailo:
    def __init__(self, model_path, camera_index=0, confidence_threshold=0.5):
        # Initialize the HailoRT SDK and open a connection to the Hailo-8L device
        self.device = hailo.Device()
        # Load the face detection model
        self.model = self.device.load_model(model_path)
        # Open the camera stream
        self.video_capture = cv2.VideoCapture(camera_index)
        # Set the confidence threshold for detections
        self.confidence_threshold = confidence_threshold
        # Get the model input shape
        self.input_shape = self.model.get_input_shape()

    def preprocess_frame(self, frame):
        # Resize the frame to match the model's input size
        resized_frame = cv2.resize(frame, (self.input_shape.width, self.input_shape.height))
        # Expand dimensions to fit the model's expected input
        return np.expand_dims(resized_frame, axis=0)

    def infer(self, input_data):
        # Perform inference using the Hailo-8L
        return self.model.infer(input_data)

    def postprocess_and_display(self, frame, results):
        # Assuming the model outputs bounding boxes and confidence scores
        detections = results[0]  # Adjust according to your model's output
        for detection in detections:
            box = detection['bbox']  # Get the bounding box
            score = detection['score']  # Get the confidence score

            # Apply a confidence threshold
            if score > self.confidence_threshold:
                # Draw the bounding box on the original frame
                cv2.rectangle(frame, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 255, 0), 2)
                label = f"Face, Score: {score:.2f}"
                cv2.putText(frame, label, (int(box[0]), int(box[1] - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Display the frame with face detection results
        cv2.imshow('Face Detection', frame)

    def run(self):
        while True:
            ret, frame = self.video_capture.read()  # Capture a frame from the camera
            if not ret:
                print("Failed to capture image from camera.")
                break

            # Preprocess the frame
            input_data = self.preprocess_frame(frame)

            # Perform inference
            results = self.infer(input_data)

            # Post-process and display the results
            self.postprocess_and_display(frame, results)

            # Exit loop when 'q' is pressed
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        # Cleanup after the loop ends
        self.video_capture.release()
        cv2.destroyAllWindows()

    def close(self):
        # Unload the model and close the Hailo device
        self.model.unload()
        self.device.close()

# Run the face detection in the main block
if __name__ == "__main__":
    # Path to your .hef model file
    model_path = 'path_to_your_face_detection_model.hef'

    # Create a FaceDetectionHailo instance
    face_detector = FaceDetectionHailo(model_path=model_path)

    try:
        # Run the face detection process
        face_detector.run()
    finally:
        # Ensure cleanup occurs even if an exception is raised
        face_detector.close()
