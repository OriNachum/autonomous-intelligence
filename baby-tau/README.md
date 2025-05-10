# Baby Tau

This is a demo project using "Best in slot" packages for voice interaction on Nvidia Jetson Orin Nano Super 8GB (fast)   
Its purpose is testing libraries on Jetson and POCing the setup.

## Setup Instructions for Jetson Orin Nano Super 8GB

### 1. Initialize and update the git submodule
```bash
git submodule update --init --recursive
git -C jetson-containers checkout dev
```

I also recommend moving to console mode:
```bash
sudo systemctl set-default multi-user.target
sudo reboot
```
A browser takes about 1GB, and GUI takes about 1.5GB.  
To switch console and gui modes:

```bash
sudo init 3
```

To revert:
```bash
sudo init 5
```

### 2. Build the container
Ensure you are in baby-tau folder
```bash
# Build the container
 ./jetson-containers/jetson-containers build --name sound-utils sound-utils
# In case of issues you can try skip tests:
# jetson-containers build --skip-tests all --name sound-utils sound-utils
```

### 3. Set the container tag
```bash
export PYTHON_TAG=$(autotag sound-utils) # Should be r36.4.3-sound-utils, can find by docker images | grep sound
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

## Citation
### dusty-nv/jetson-containers
```
cff-version: 1.2.0
title: >-
  Jetson Containers(Machine Learning Containers for Jetson and JetPack)
message: >-
  If you use this software, please cite it using the
  metadata from this file.
type: software
authors:
  - given-names: Dustin
    family-names: Franklin
    affiliation: Nvidia
repository-code: 'https://github.com/dusty-nv/jetson-containers'
url: 'https://www.jetson-ai-lab.com/'
abstract: Machine Learning Containers for Jetson and JetPack
license: MIT
```
