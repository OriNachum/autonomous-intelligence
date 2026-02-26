"""FastAPI app + uvicorn entrypoint."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .ws_handler import handle_realtime_ws

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
# In Docker the package is installed, so fall back to /app/static
if not STATIC_DIR.exists():
    STATIC_DIR = Path("/app/static")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

app = FastAPI(title="OpenAI Realtime API Bridge", version="0.1.0")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/v1/realtime")
async def realtime_ws(ws: WebSocket, model: str = Query(default=None)):
    await handle_realtime_ws(ws, model=model)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main():
    log.info("Starting Realtime API on %s:%d", settings.host, settings.port)
    uvicorn.run(
        "realtime_api.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
