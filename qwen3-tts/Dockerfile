FROM nvcr.io/nvidia/pytorch:25.11-py3

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install NeMo TTS and server dependencies
RUN pip install --no-cache-dir \
    "nemo_toolkit[tts] @ git+https://github.com/NVIDIA/NeMo.git" \
    kaldialign \
    soundfile>=0.13.1 \
    fastapi \
    "uvicorn[standard]"

# Copy server code
WORKDIR /app
COPY src/server.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=300s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
