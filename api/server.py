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

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api import agents_web, forecast

app = FastAPI(title="Intelligent Forecast", version="1.0.0")

# Allow the Vite dev server (localhost:5173) to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    query: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/forecast")
def get_forecast() -> dict:
    return forecast.full_payload()


@app.post("/api/ask")
def post_ask(req: AskRequest) -> dict:
    return agents_web.ask(req.query, forecast.flagged_deals())


# Serve the built React app if it exists (production). In dev, use the Vite
# server on :5173 and hit the API directly.
_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
