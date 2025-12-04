# Vision Integration Plan

This plan outlines the steps to integrate vision events into the conversation flow, ensuring that visual context is available for AI requests triggered by speech, and implementing a robust filtering mechanism to reduce event noise.

## Goal
1.  **Cache Vision Events**: Ensure the latest visual context is included in the AI request triggered by speech events.
2.  **Vision Filtering**: Implement a stability filter (average > 50% over 1 second) to only emit vision events when significant changes occur, preventing flickering.

## User Review Required
> [!IMPORTANT]
> **Filtering Logic**: The proposed filter uses a 1-second sliding window. An object is considered "present" only if detected in >50% of frames within this window. This introduces a slight latency (up to 1 second) for detection updates but significantly increases stability.

## Proposed Changes

### 1. Vision Filtering (Processor Layer)
We will implement a filtering mechanism within `ProcessorManager` to stabilize detection results before emitting them.

#### [MODIFY] [manager.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/processors/manager.py)
-   Add a `ResultFilter` class (or inner class) to handle the sliding window logic.
-   **Logic**:
    -   Maintain a `deque` of the last N results (corresponding to ~1 second).
    -   For object detection (YOLO):
        -   Flatten detections to a set of labels per frame.
        -   Count occurrences of each label across the window.
        -   Threshold: Label is "valid" if count > (window_size * 0.5).
    -   Compare current "valid" set with the previously emitted set.
    -   **Only emit event if the set changes.**
-   Update `process_stream_frame` to use this filter before calling `emit_event`.

### 2. Vision Caching & Integration (Application Layer)
We will update the main application to listen for these stabilized vision events, cache them, and inject them into the conversation context.

#### [MODIFY] [app.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/app.py)
-   **Update `on_gateway_event`**:
    -   Add handling for `yolo_v8_result` (and potentially `face_recognition_result`).
    -   Store the latest result in a new attribute: `self.latest_vision_context`.
        -   Structure: `{'objects': ['person', 'cup'], 'timestamp': 1234567890}`
-   **Update `process_message`**:
    -   When constructing the `user_message` from speech:
        -   Check `self.latest_vision_context`.
        -   If valid (and recent enough, e.g., < 5 seconds old?), append visual context.
        -   Format: `*Heard from ...* "Hello" *[Visual Context: I see a person and a cup]*`
    -   This ensures the model knows what is currently visible when the user speaks.

## Verification Plan

### Automated Tests
-   **Unit Test for Filter**:
    -   Create `tests/test_vision_filter.py`.
    -   Simulate a sequence of frames: `[None, 'cup', 'cup', 'cup', None, 'cup']`.
    -   Verify that the "stable state" transitions correctly and ignores transient dropouts.
    -   Verify that events are only emitted on state change.

### Manual Verification
1.  **Start the Application**: Run `python -m conversation_app.app`.
2.  **Test Filtering**:
    -   Show an object (e.g., a cup) to the camera.
    -   Observe logs: Should see *one* "Vision event: ['cup']" (or similar).
    -   Hide the object.
    -   Observe logs: Should see *one* "Vision event: []".
    -   Verify no "flickering" events are logged while the object is held steady.
3.  **Test Integration**:
    -   Show an object (e.g., "I see a cup").
    -   Speak to the robot: "What do you see?"
    -   Verify the model's response mentions the object (e.g., "I see a cup").
    -   Check logs to confirm the `user_message` sent to LLM included the visual context tag.
