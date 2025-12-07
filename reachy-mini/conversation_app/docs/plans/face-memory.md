# Face Memory Feature Plan

## Overview
This feature enables the robot to learn new faces dynamically. When it sees an unknown face, it assigns a temporary ID (e.g., "JohnDoe1") and saves the face image. The user can then provide a name for this face, and the robot will update its memory.

## Workflow

1.  **Detection & Storage**:
    -   The `FaceRecognitionProcessor` detects a face.
    -   If the face matches a known encoding, it returns the name.
    -   If the face is unknown:
        -   It checks if it's a "stable" detection (optional, for now we might just save on first clear view).
        -   It generates a new ID: `JohnDoe<NextNumber>`.
        -   It creates a folder `data/faces/JohnDoe<NextNumber>`.
        -   It saves the cropped face image to this folder.
        -   It reloads its known faces to include this new one.
        -   It returns `JohnDoe<NextNumber>` as the name.

2.  **Notification**:
    -   The `ProcessorManager` emits a `face_recognition_result` event with the new name.
    -   The `ConversationApp` receives this event and updates the context.
    -   The robot might say "I see someone new, I'll call them JohnDoe1 for now." (This depends on the prompt/logic, but the capability is there).

3.  **Naming**:
    -   The user says "JohnDoe1 is actually Alice" or "That person is Alice".
    -   The LLM calls the `name_face` tool with `current_name="JohnDoe1"` and `new_name="Alice"`.
    -   The `name_face` action:
        -   Renames `data/faces/JohnDoe1` to `data/faces/Alice`.
        -   Triggers a reload of the vision models.
    -   Future detections will identify the face as "Alice".

## Implementation Details

### `FaceRecognitionProcessor`
-   **Path**: `conversation_app/processors/face.py`
-   **Changes**:
    -   `_get_next_johndoe_id()`: Helper to find the next available number.
    -   `process()`: Logic to save unknown faces.
    -   `save_face(image, location, name)`: Helper to save the image.

### `GatewayVideo` & `ReachyGateway`
-   **Path**: `conversation_app/gateway_video.py`, `conversation_app/gateway.py`
-   **Changes**:
    -   Expose methods to trigger `processor.initialize()` (reload).

### `name_face` Action
-   **Path**: `conversation_app/actions/name_face.json`, `conversation_app/actions/scripts/name_face.py`
-   **Logic**: File system rename + Gateway reload call.

## Data Structure
-   `data/faces/`
    -   `Alice/`
        -   `image1.jpg`
    -   `Bob/`
        -   `image1.jpg`
    -   `JohnDoe1/`
        -   `image1.jpg`
