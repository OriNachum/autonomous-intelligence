FROM reachy-conversation-full:r38.2.arm64-sbsa-cu130-24.04

WORKDIR /app

#    cmake \
# Install system dependencies
RUN apt-get update -qq && \
    apt-get install -y -qq alsa-utils \
    v4l-utils \
    build-essential \
    libx11-dev \
    libopenblas-dev \
    pkg-config \
    python3-dev \
    libgirepository1.0-dev \
    libcairo2-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-alsa \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-base-apps \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-gst-plugins-bad-1.0 \
    gir1.2-gudev-1.0 \
    v4l-utils \
    libssl-dev \
    python3-gi \
    python3-gst-1.0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

# Install Rust (Standard Rustup)
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN git clone https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs.git && \
    cd gst-plugins-rs && \
    # Checkout a stable tag compatible with your GStreamer version (optional, but safer)
    # git checkout 0.11.3 && \
    # Build ONLY the webrtc plugin (Saves massive time)
    cargo build --release --package gst-plugin-webrtc --locked && \
    # Install the shared object (.so) to the system plugin path
    cp target/release/*.so /usr/lib/aarch64-linux-gnu/gstreamer-1.0/ && \
    # Cleanup to keep image small
    cd /app && \
    rm -rf /tmp/gst-plugins-rs ~/.cargo

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

    
#    git checkout v19.24 && \
RUN git clone https://github.com/davisking/dlib.git && \
    cd dlib && \
    python3 setup.py install && \
    cd .. && \
    rm -rf dlib

# Copy requirements files
COPY conversation_app/requirements.txt /app/conversation_app/requirements.txt

RUN echo "TEST"

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/conversation_app/requirements.txt 

# Copy application code
COPY . /app
#RUN sed -i 's/api.v4l2.path/device.path/g' \
#    /opt/venv/lib/python3.12/site-packages/reachy_mini/media/camera_gstreamer.py && \
RUN echo 'pcm.!default { type plug slave.pcm "hw:Audio,0" }' > /etc/asound.conf && \
    echo 'ctl.!default { type hw card Audio }' >> /etc/asound.conf

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# Add this near your other ENV command
ENV GI_TYPELIB_PATH=/usr/lib/aarch64-linux-gnu/girepository-1.0:/usr/lib/girepository-1.0
# Force ALSA default device to be the USB Card named "Audio"
# This makes autoaudiosrc pick the correct microphone automatically.
CMD ["python3", "-m", "conversation_app.app"]
