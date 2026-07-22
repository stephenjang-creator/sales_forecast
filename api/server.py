"""FastAPI app for Intelligent Forecast: JSON API + the built React dashboard.

Endpoints:
  GET  /api/health         -> {"status": "ok"}
  GET  /api/forecast       -> full dashboard payload (deals, kpis, scorecard, ...)
  POST /api/ask            -> {"query": "..."} routes to an agent, returns {agent,text}
  GET  /                   -> the built React app (web/dist), if present

Run locally:  uvicorn api.server:app --reload --port 8000
The core is offline; set ANTHROPIC_API_KEY to enable LLM-backed agent answers.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api import agents_web, forecast

# Serve the built React app if it exists (production). In dev, use the Vite
# server on :5173 and hit the API directly.
_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
_log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Logged on every boot so a "Not Found" at the root is a one-line diagnosis
    # in the deploy logs instead of guesswork.
    if _DIST.is_dir() and (_DIST / "index.html").is_file():
        _log.info("Intelligent Forecast: serving built SPA from %s", _DIST)
    else:
        _log.warning(
            "Intelligent Forecast: web/dist not found at %s -- API is up but the "
            "root path will 404. Rebuild the image so the SPA is bundled.",
            _DIST,
        )
    yield


app = FastAPI(title="Intelligent Forecast", version="1.0.0", lifespan=lifespan)

# Allow the Vite dev server (localhost:5173) to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    query: str
    # Optional bring-your-own Anthropic key: used only to answer THIS request and
    # never stored, logged, or persisted server-side.
    apiKey: str | None = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/forecast")
def get_forecast() -> dict:
    payload = forecast.full_payload()
    # Tell the UI whether the server already has a key (so it can offer LLM answers
    # directly) or is in demo mode (so it can invite a bring-your-own key).
    payload["serverHasKey"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return payload


@app.post("/api/ask")
def post_ask(req: AskRequest) -> dict:
    # req.apiKey is passed straight through for a single call and never retained.
    return agents_web.ask(req.query, forecast.flagged_deals(), api_key=req.apiKey)


if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
