#FROM reachy-hearing-thor:r38.2.arm64-sbsa-cu130-24.04
FROM reachy-conversation-full:r38.2.arm64-sbsa-cu130-24.04

WORKDIR /app

# Install system dependencies
RUN apt-get update -qq && \
    apt-get install -y -qq alsa-utils \
# 1. The Build Tools (You had these)
    build-essential \
    pkg-config \
    python3-dev \
    libgirepository1.0-dev \
    libcairo2-dev \
    # 2. THE MISSING PIECE: GStreamer Libraries & Headers
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
    # 3. The Introspection Data (CRITICAL for Python "import Gst")
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-gst-plugins-bad-1.0 \
    python3-gi \
    python3-gst-1.0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN git clone https://github.com/pollen-robotics/gst-signalling-py.git && \
    cd gst-signalling-py && \
    git checkout v1.1.2 && \
    # HACK 1: Relax PyGObject to accept the system version (usually 3.42.1)
    #sed -i 's/PyGObject>=3.42.2/PyGObject>=3.40.0/' setup.cfg && \
    # HACK 2: Relax Numpy just in case your base image has an older version (e.g. 1.21)
    sed -i 's/numpy>=1.24.0,<=2.2.5/numpy>=2.3.5/' setup.cfg && \
    # Install from the current directory
    pip install . && \
    # Cleanup
    cd /app && \
    rm -rf /tmp/gst-signalling-py

# Copy requirements files
COPY conversation_app/requirements.txt /app/conversation_app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/conversation_app/requirements.txt 

# Copy application code
COPY . /app

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# Add this near your other ENV command
ENV GI_TYPELIB_PATH=/usr/lib/aarch64-linux-gnu/girepository-1.0:/usr/lib/girepository-1.0

CMD ["python3", "-m", "conversation_app.app"]
