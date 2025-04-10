# Baby Tau

This is a demo project using "Best in slot" packages for voice interaction on Nvidia Jetson Orin Nano Super 8GB (fast)   
Its purpose is testing libraries on Jetson and POCing the setup.

## Setup Instructions for Jetson Orin Nano Super 8GB

### 1. Initialize and update the git submodule
```bash
git submodule update --init --recursive
git -C packages checkout silerovad-library
```

### 2. Build the container
```bash
# Build the container with CUDA 12.8
jetson-containers build --cuda 12.8 all --name silerovad silerovad
# Or alternatively skip tests
# jetson-containers build --skip-tests all --name silerovad silerovad
```

### 3. Set the container tag
```bash
export CONTAINER_TAG=$(autotag silerovad)
```

### 4. Configure and validate
- Edit the `.env` file to set your preferred LLM model
- Validate the configuration
  
### 5. Start the services
```bash
docker compose up
```

## Usage
Once the docker compose is running, you can simply speak into your microphone. The system will:
1. Detect voice activity using SileroVAD
2. Transcribe your speech using Speaches (Faster Whisper)
3. Process with the LLM using vllm
4. Convert the response to speech via KokoroTTS
5. Play the response through your speakers

No additional commands needed - just speak and listen!

## Components
- SileroVAD - Voice Activity Detection
- Speaches (Faster Whisper) - Speech recognition
- vllm - Large Language Model inference
- KokoroTTS fastapi - Text-to-Speech

These are all "Best in slow" packages optimized for Jetson devices.

