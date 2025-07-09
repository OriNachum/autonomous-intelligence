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

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all

# Expose the API port
EXPOSE 8000

# Run the application
CMD ["python3", "app.py"]