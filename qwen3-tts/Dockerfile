FROM scitrera/dgx-spark-vllm:0.16.0-t4

# System deps (ffmpeg, sox for audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg sox \
    && rm -rf /var/lib/apt/lists/*

# Clone vllm-omni, remove fa3-fwd (not available for aarch64), install
RUN git clone https://github.com/vllm-project/vllm-omni.git /opt/vllm-omni \
    && cd /opt/vllm-omni \
    && sed -i '/fa3-fwd/d' requirements/cuda.txt \
    && pip install --no-cache-dir --no-deps -e . \
    && pip install --no-cache-dir \
    omegaconf resampy diffusers accelerate gradio soundfile \
    cache-dit torchsde openai-whisper imageio sox prettytable \
    aenum onnxruntime "imageio[ffmpeg]" librosa

WORKDIR /opt/vllm-omni

# Custom stage config with reduced GPU memory for DGX Spark unified memory
COPY stage_configs/qwen3_tts.yaml /opt/vllm-omni/stage_configs/qwen3_tts.yaml

# Default: serve CustomVoice model
ENV QWEN3_TTS_MODEL="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
ENV QWEN3_TTS_PORT="8091"

EXPOSE ${QWEN3_TTS_PORT}

CMD vllm serve "$QWEN3_TTS_MODEL" \
    --stage-configs-path stage_configs/qwen3_tts.yaml \
    --omni \
    --port "$QWEN3_TTS_PORT" \
    --trust-remote-code \
    --enforce-eager
