# Plan: Optimize Whisper STT and Docker Configuration

## Goal Description
Improve the performance and reliability of the `reachy-conversation` service by:
1.  Using a locally downloaded Whisper `large-v3` model to avoid repeated downloads and potential hangs.
2.  Refactoring `conversation_app/whisper_stt.py` to accept a local model path.
3.  Creating a `Dockerfile` to bake dependencies into the image, removing runtime `pip install`s.
4.  Updating `docker-compose-vllm.yml` to mount the model and use the new Docker image.

## User Review Required
> [!IMPORTANT]
> This plan involves downloading a large model (~3GB) to the host machine. Ensure you have sufficient disk space.

## Proposed Changes

### Host Machine
#### [NEW] Download Script
Run the following commands on the host to download the model:
```bash
mkdir -p ./data/whisper_models/large-v3
huggingface-cli download Systran/faster-whisper-large-v3 \
  --local-dir ./data/whisper_models/large-v3 \
  --local-dir-use-symlinks False
```

### Conversation App
#### [MODIFY] [whisper_stt.py](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/whisper_stt.py)
- Update `__init__` to accept `model_path_or_size`.
- Use `local_files_only=True` when loading the model to ensure it uses the mounted path.
- Add logging to confirm model loading source.
- Update `transcribe` loop to prevent blocking on generator.

### Docker Configuration
#### [NEW] [Dockerfile](file:///home/thor/git/autonomous-intelligence/reachy-mini/conversation_app/Dockerfile)
- Base image: `reachy-hearing-thor:r38.2.arm64-sbsa-cu130-24.04` (or `python:3.10-slim` if preferred, but sticking to existing base for compatibility).
- Copy `conversation_app/requirements.txt` and `gateway_app/requirements.txt`.
- Install dependencies.
- Copy application code.

#### [MODIFY] [docker-compose-vllm.yml](file:///home/thor/git/autonomous-intelligence/reachy-mini/docker-compose-vllm.yml)
- Update `reachy-conversation` service:
    - Build from the new `Dockerfile`.
    - Mount `./data/whisper_models` to `/data/models/whisper`.
    - Set `WHISPER_MODEL_PATH` environment variable.
    - Remove `pip install` commands from `command`.

## Verification Plan

### Automated Tests
- None available for this specific integration.

### Manual Verification
1.  **Download Model**: Run the download commands and verify files exist in `./data/whisper_models/large-v3`.
2.  **Build & Start**: Run `docker compose -f docker-compose-vllm.yml up --build -d reachy-conversation`.
3.  **Check Logs**: `docker compose -f docker-compose-vllm.yml logs -f reachy-conversation`.
    - Verify "Whisper model loaded successfully" log.
    - Verify no "Downloading..." logs for Whisper.
4.  **Test Transcription**: Speak to the robot and verify transcription logs appear without hanging.
