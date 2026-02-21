"""MagpieTTS FastAPI server.

Loads the model once at startup and keeps it warm in GPU memory.
Exposes /health and /synthesize endpoints.
"""

import io
import logging
from contextlib import asynccontextmanager

import soundfile as sf
import torch
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

logger = logging.getLogger("magpietts")

SPEAKERS = {
    "John": 0,
    "Sofia": 1,
    "Aria": 2,
    "Jason": 3,
    "Leo": 4,
}

LANGUAGES = {"en", "es", "de", "fr", "vi", "it", "zh"}

MODEL_ID = "nvidia/magpie_tts_multilingual_357m"
SAMPLE_RATE = 22050

_model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    logger.info("Loading MagpieTTS model %s ...", MODEL_ID)
    from nemo.collections.tts.models import MagpieTTSModel

    _model = MagpieTTSModel.from_pretrained(MODEL_ID)
    _model = _model.to("cuda:0")
    _model.eval()
    logger.info("Model loaded and ready.")
    yield
    _model = None


app = FastAPI(title="MagpieTTS", lifespan=lifespan)


class SynthesizeRequest(BaseModel):
    message: str
    speaker: str = "Aria"
    language: str = "en"


@app.get("/health")
async def health():
    if _model is None:
        return JSONResponse({"status": "loading"}, status_code=503)
    return {"status": "ok"}


@app.post("/synthesize")
async def synthesize(req: SynthesizeRequest):
    if _model is None:
        return JSONResponse({"error": "Model not loaded yet"}, status_code=503)

    speaker_idx = SPEAKERS.get(req.speaker, 2)
    lang = req.language if req.language in LANGUAGES else "en"

    try:
        audio, audio_len = _model.do_tts(
            req.message,
            language=lang,
            apply_TN=False,
            speaker_index=speaker_idx,
        )
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        return JSONResponse({"error": "GPU out of memory"}, status_code=500)

    wav = audio[0, : audio_len[0]].cpu().numpy()

    buf = io.BytesIO()
    sf.write(buf, wav, SAMPLE_RATE, format="WAV")
    buf.seek(0)

    return Response(content=buf.read(), media_type="audio/wav")
