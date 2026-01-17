FROM nvcr.io/nvidia/pytorch:25.11-py3

# Install Unsloth dependencies
RUN pip install --no-cache-dir \
    transformers \
    peft \
    hf_transfer \
    "datasets==4.3.0" \
    "trl==0.26.1" && \
    pip install --no-cache-dir --no-deps \
    unsloth \
    unsloth_zoo \
    bitsandbytes

# Download test script
RUN curl -O https://raw.githubusercontent.com/NVIDIA/dgx-spark-playbooks/refs/heads/main/nvidia/unsloth/assets/test_unsloth.py

WORKDIR /workspace
