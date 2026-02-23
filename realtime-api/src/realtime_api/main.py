"""FastAPI app + uvicorn entrypoint."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI, Query, WebSocket

from .config import settings
from .ws_handler import handle_realtime_ws

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

app = FastAPI(title="OpenAI Realtime API Bridge", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/v1/realtime")
async def realtime_ws(ws: WebSocket, model: str = Query(default=None)):
    await handle_realtime_ws(ws, model=model)


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
