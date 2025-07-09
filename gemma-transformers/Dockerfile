# Use NVIDIA L4T PyTorch base image for Jetson
ARG BASE_IMAGE=dustynv/pytorch:2.1-r36.2.0
FROM ${BASE_IMAGE}

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
# Note: Some packages might need special handling for ARM64
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY model_handler.py .
COPY download_model.py .
COPY entrypoint.sh .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all
ENV HF_HOME=/cache/huggingface
ENV TRANSFORMERS_CACHE=/cache/huggingface

# Create cache directories with proper permissions
RUN mkdir -p /cache/huggingface /models /app/logs && \
    chmod -R 777 /cache /models /app/logs

# Expose the API port
EXPOSE 8000

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]