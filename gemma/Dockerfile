# Gemma Multimodal AI Assistant Docker Image
FROM nvcr.io/nvidia/pytorch:23.10-py3

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gstreamer1.0-x \
    gstreamer1.0-alsa \
    gstreamer1.0-gl \
    gstreamer1.0-gtk3 \
    gstreamer1.0-qt5 \
    gstreamer1.0-pulseaudio \
    libopencv-dev \
    python3-opencv \
    portaudio19-dev \
    alsa-utils \
    pulseaudio \
    espeak \
    espeak-data \
    libespeak-dev \
    ffmpeg \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for containerized environment
RUN pip install --no-cache-dir \
    jupyterlab \
    ipywidgets \
    matplotlib \
    seaborn \
    plotly

# Copy application code
COPY src/ ./src/
COPY run_gemma.py .
COPY README.md .

# Create directories for models and data
RUN mkdir -p /app/models /app/data /app/logs

# Set up audio group and permissions
RUN groupadd -r audio && \
    usermod -a -G audio root

# Create startup script
RUN echo '#!/bin/bash\n\
# Start PulseAudio in daemon mode\n\
pulseaudio --start --log-target=newfile:/tmp/pulse.log --log-level=info\n\
\n\
# Wait for PulseAudio to start\n\
sleep 2\n\
\n\
# List audio devices for debugging\n\
echo "Available audio devices:"\n\
pactl list short sources\n\
pactl list short sinks\n\
\n\
# Start Gemma\n\
exec python run_gemma.py\n\
' > /app/start.sh && chmod +x /app/start.sh

# Environment variables for configuration
ENV GEMMA_LOG_LEVEL=INFO
ENV GEMMA_CAMERA_DEVICE=0
ENV GEMMA_AUDIO_SAMPLE_RATE=16000
ENV GEMMA_WAKE_WORDS="Gemma,Hey Gemma"
ENV GEMMA_TTS_ENGINE=espeak
ENV GEMMA_MODEL_NAME=microsoft/DialoGPT-medium
ENV GEMMA_MODEL_CACHE_DIR=/app/models
ENV GEMMA_EVENT_SOCKET_PATH=/tmp/gemma_events.sock

# Expose ports (if needed for web interface)
EXPOSE 8888 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import socket; s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect('/tmp/gemma_events.sock'); s.close()" || exit 1

# Default command
CMD ["/app/start.sh"]