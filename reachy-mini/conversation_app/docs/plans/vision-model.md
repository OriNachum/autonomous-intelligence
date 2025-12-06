# Vision Model Integration Plan

This plan outlines the changes required to update `conversation_app/app.py` to support the **Qwen 2.5 VL 7B Instruct** model, enabling multimodal inputs (text + image) via an OpenAI-compatible interface.

## Goal
1.  **Enable Vision Capabilities**: Send the latest captured video frame along with the user's speech to the model.
2.  **Support Multimodal Messages**: Update the API request payload to use the `{"type": "text", ...}, {"type": "image_url", ...}` format.
3.  **Adapt to New Model**: Ensure compatibility with Qwen 2.5 VL 7B Instruct and its specific requirements (e.g., Hermes parser compatibility if applicable).

## User Review Required
> [!IMPORTANT]
> **Image Transmission**: We will use **Base64 encoding** to send images to the local vLLM server. This ensures compatibility regardless of whether the server can access the local file system directly.
>
> **Parser Compatibility**: The user mentioned using "hermes parser". We will assume this requires verifying that the model's output format (which might be XML-structured or standard text) is correctly parsed by our `ConversationParser`. If the model uses specific Hermes-style tags (e.g., `<tool_code>`), we may need to update `conversation_parser.py`.

## Proposed Changes

### 1. Image Handling & Message Construction
We need to modify how user messages are constructed and sent to the API.

#### [MODIFY] [app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
-   **Helper Method**: Add `_encode_image_to_base64(image_path)` to convert local frames to data URLs.
-   **Update `process_message`**:
    -   Retrieve the latest frame from `self.recent_frames`.
    -   If a recent frame exists (e.g., < 5 seconds old), encode it.
    -   Construct the `content` list:
        ```python
        content = [{"type": "text", "text": user_message}]
        if image_base64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
        ```
    -   Update the `messages` list to store this structured content instead of a simple string.
-   **Update `chat_completion_stream`**:
    -   Ensure `httpx` payload correctly handles the list-based `content` (standard JSON serialization should work).

### 2. Configuration Update
Ensure the model name matches the new requirement.

#### [MODIFY] [app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
-   Update default `MODEL_NAME` to `RedHatAI/Qwen2.5-VL-7B-Instruct-quantized.w4a16` (or keep using `os.environ` but update the default fallback).

### 3. Parser Verification (Hermes Support)
Since the user mentioned "hermes parser", we should ensure our parser can handle the output.

#### [MODIFY] [conversation_parser.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/conversation_parser.py)
-   *Conditional*: If the new model outputs Hermes-style XML (e.g., `<scratchpad>`, `<tool_code>`), we will need to update `parse_token` to handle these tags or strip them if they are not needed for speech/actions.
-   *Plan*: Initially, we will test with the existing parser. If the model outputs standard text/quotes, no change is needed. If it uses XML, we will add XML tag handling.

## Verification Plan

### Manual Verification
1.  **Start the App**: Run `python -m conversation_app.app`.
2.  **Trigger Speech**: Speak to the robot (e.g., "What do you see?").
3.  **Verify Request**:
    -   Check logs to confirm the API request includes `image_url` with base64 data.
    -   Confirm the `model` parameter is correct.
4.  **Verify Response**:
    -   Check if the model responds accurately to the visual input (e.g., describing the object in front of the camera).
    -   Verify that speech and actions are correctly parsed and executed.

### Automated Tests
-   We can add a test case in `tests/test_app.py` (if it exists) or a new test script to mock `httpx` and verify the payload structure includes the image.
