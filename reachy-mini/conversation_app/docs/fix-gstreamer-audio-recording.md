# Fix GStreamer Audio Recording Speed Issue

## Problem Description
The audio recording and processing is running at "double speed" (chipmunk effect). This occurs because the audio is being captured at **8000 Hz** (likely default for the GStreamer pipeline or device) but is being processed and saved as **16000 Hz**.

- **Capture**: 8000 samples per second.
- **Processing/Saving**: Treating those 8000 samples as if they span 0.5 seconds of 16000 Hz audio.
- **Result**: Audio plays back 2x faster.

## Proposed Fix
The fix is to modify `conversation_app/gateway_audio.py` to automatically detect the actual sample rate from the `ReachyController` instead of relying on the hardcoded default or environment variable.

Both **Silero VAD** and **Whisper STT** support 8000 Hz audio, so we can simply propagate the detected rate through the pipeline without needing complex resampling.

### Code Changes

#### `conversation_app/gateway_audio.py`

Modify the `__init__` method of `GatewayAudio` to query the sample rate from `reachy_controller`.

```python
# In conversation_app/gateway_audio.py

class GatewayAudio:
    def __init__(self, reachy_controller, event_callback, language='en'):
        # ... existing initialization ...
        
        self.reachy_controller = reachy_controller
        self.emit_event = event_callback
        self.language = language
        
        # --- NEW CODE START ---
        # Detect actual sample rate from controller
        detected_rate = 16000  # Default fallback
        if self.reachy_controller:
            try:
                # This gets the actual rate from the GStreamer pipeline
                detected_rate = self.reachy_controller.get_sample_rate()
                logger.info(f"Detected audio sample rate from controller: {detected_rate} Hz")
            except Exception as e:
                logger.warning(f"Could not get sample rate from controller: {e}")
        
        # Use detected rate, but allow override via env var if explicitly set to something else
        # (Note: We prioritize the detected rate if env var is just the default '16000')
        env_rate = int(os.getenv('SAMPLE_RATE', '16000'))
        
        if env_rate != 16000 and env_rate != detected_rate:
            logger.warning(f"Environment SAMPLE_RATE ({env_rate}) differs from detected rate ({detected_rate}). Using Environment value.")
            self.rate = env_rate
        else:
            if detected_rate != 16000:
                logger.info(f"Using detected sample rate {detected_rate} Hz instead of default 16000 Hz")
            self.rate = detected_rate
            
        # Update chunk size calculation with the correct rate
        self.chunk_duration_ms = int(os.getenv('CHUNK_DURATION_MS', '30'))
        self.chunk_size = int(self.rate * self.chunk_duration_ms / 1000)
        logger.info(f"Audio Configuration: Rate={self.rate}Hz, Chunk={self.chunk_duration_ms}ms ({self.chunk_size} samples)")
        # --- NEW CODE END ---
        
        # ... rest of initialization (VAD, STT) uses self.rate ...
        # self.vad = SileroVAD(..., sample_rate=self.rate)
        # self.whisper = WhisperSTT(..., self.rate)
```

### Alternative: Configuration-only Fix
If you prefer not to change the code immediately, you can try setting the `SAMPLE_RATE` environment variable to `8000` in your `docker-compose.yml`.

```yaml
services:
  conversation_app:
    environment:
      - SAMPLE_RATE=8000
```

However, the code fix is recommended as it makes the system robust to different hardware configurations (e.g., if you switch to a 48kHz microphone later).

## Verification
1.  **Deploy the fix**: Apply the code changes and rebuild/restart the container.
2.  **Check Logs**: Look for the log line: `Detected audio sample rate from controller: 8000 Hz` (or whatever the actual rate is).
3.  **Test Audio**: Speak "1, 2, 3, 4, 5".
4.  **Verify Transcription**: Ensure the system correctly transcribes "1, 2, 3, 4, 5" and not a truncated or garbled version.
5.  **Verify Recording**: Check the saved WAV files in `recordings/`. They should sound normal speed when played back.
