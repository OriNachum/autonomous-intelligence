# Unsloth on DGX Spark

Optimized fine-tuning with Unsloth for up to 2x faster training speeds with reduced memory usage.

## Quick Start

```bash
cd unsloth/spark
sudo docker compose run --rm unsloth
```

Inside the container:
```bash
python scripts/train.py
```

## Configuration

Edit `.env` to customize training:

```bash
# Model settings
MODEL_NAME=unsloth/gemma-3-4B-it
MAX_SEQ_LENGTH=2048
LOAD_IN_4BIT=true

# Training settings
BATCH_SIZE=2
GRADIENT_ACCUMULATION_STEPS=4
MAX_STEPS=60
LEARNING_RATE=5e-5

# LoRA settings
LORA_R=16
LORA_ALPHA=16

# For gated models (Llama, etc.)
HF_TOKEN=hf_...
```

## Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./data` | `/workspace/data` | Your datasets (place `train.jsonl` here) |
| `./outputs` | `/workspace/outputs` | Fine-tuned models saved here |
| `./scripts` | `/workspace/scripts` | Custom training scripts |

# Adjust training parameters (line 61)
per_device_train_batch_size = 4
max_steps = 1000
```

## Resources

- [Unsloth Documentation](https://docs.unsloth.ai/)
- [Unsloth Wiki](https://github.com/unslothai/unsloth/wiki)
- [DGX Spark Documentation](https://docs.nvidia.com/dgx/dgx-spark)

---

## Source

Installation guide from: https://build.nvidia.com/spark/unsloth

## Installation Steps Performed

**Date**: 2026-01-17

### Prerequisites Verified

```bash
nvcc --version   # CUDA 13.0
nvidia-smi       # NVIDIA GB10 GPU
```

### Step 1: Pull the PyTorch Container

```bash
sudo docker pull nvcr.io/nvidia/pytorch:25.11-py3
```

### Step 2: Launch Container and Install Unsloth

```bash
sudo docker run --gpus all --ulimit memlock=-1 -it --ulimit stack=67108864 \
  --entrypoint /usr/bin/bash --rm nvcr.io/nvidia/pytorch:25.11-py3 \
  -c "pip install transformers peft hf_transfer 'datasets==4.3.0' 'trl==0.26.1' && \
      pip install --no-deps unsloth unsloth_zoo bitsandbytes && \
      curl -O https://raw.githubusercontent.com/NVIDIA/dgx-spark-playbooks/refs/heads/main/nvidia/unsloth/assets/test_unsloth.py && \
      python test_unsloth.py"
```

### Validation Results

| Component | Version/Details |
|-----------|-----------------|
| Unsloth | 2026.1.3 |
| bitsandbytes | 0.49.1 |
| transformers | 4.57.6 |
| peft | 0.18.1 |
| trl | 0.26.1 |
| Test Model | unsloth/gemma-3-4b-it-bnb-4bit |
| Training Steps | 60/60 ✅ |
| Runtime | 99.5 seconds |
| Final Loss | 1.94 |
