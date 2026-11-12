"""Serveur web : page de chat + API en streaming (Server-Sent Events).

Lancement : uvicorn app.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from typing import Optional

from pydantic import BaseModel

from . import config
from .agent import Assistant, LimiteurDebit

STATIC = config.ROOT / "app" / "static"

app = FastAPI(title="Assistant SGO IMMO", docs_url=None, redoc_url=None)
app.state.assistant = Assistant()
app.state.limiteur = LimiteurDebit(config.MESSAGES_PAR_HEURE_PAR_IP)


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


def _sse(evt: dict) -> str:
    return f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
async def public_config():
    return {"conseiller": config.CONSEILLER, "contact": config.CONTACT}


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    message = req.message.strip()
    if not message:
        return JSONResponse({"error": "Message vide."}, status_code=400)
    if len(message) > config.MAX_CARACTERES_MESSAGE:
        return JSONResponse({"error": f"Message trop long (maximum {config.MAX_CARACTERES_MESSAGE} caractères)."},
                            status_code=400)
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    if not request.app.state.limiteur.autoriser(ip.strip()):
        return JSONResponse({"error": "Trop de messages en peu de temps. Réessayez plus tard."}, status_code=429)

    async def flux():
        async for evt in request.app.state.assistant.repondre(req.conversation_id, message):
            yield _sse(evt)

    return StreamingResponse(flux(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
