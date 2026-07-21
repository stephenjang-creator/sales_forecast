# Deploying Intelligent Forecast

The app ships as **one container**: a FastAPI backend serves the JSON API *and*
the built React dashboard from the same origin. You deploy the image anywhere
that runs Docker and set one optional environment variable.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | optional | Enables LLM-backed answers in the "Ask anything" agent bar. **Without it the app still works fully** — agents fall back to deterministic answers computed from the real data. |
| `PORT` | optional | Port to bind (default `8000`). Most hosts inject this automatically. |
| `FORECAST_CSV` | optional | Path to a different pipeline CSV (default: the bundled `data/pipeline.csv`). |
| `FORECAST_AGENT_MODEL` | optional | Anthropic model id for agent answers (default `claude-sonnet-4-6`). |

The API is read-only and makes no outbound calls unless `ANTHROPIC_API_KEY` is set.

## Build & run locally

```bash
docker build -t intelligent-forecast .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-... intelligent-forecast
# open http://localhost:8000
```

Omit `-e ANTHROPIC_API_KEY` to run fully offline (deterministic agent answers).

## Deploy to a managed host

Any Docker host works. Common one-click options:

- **Render** — New → Web Service → "Deploy an existing image" or connect the
  repo (it auto-detects the `Dockerfile`). Set `ANTHROPIC_API_KEY` under
  Environment. Render injects `PORT`.
- **Railway** — New Project → Deploy from repo. It builds the `Dockerfile` and
  injects `PORT`. Add `ANTHROPIC_API_KEY` under Variables.
- **Fly.io** — `fly launch` (detects the Dockerfile), then
  `fly secrets set ANTHROPIC_API_KEY=sk-...` and `fly deploy`.

## Local development (hot reload)

Run the two dev servers side by side; Vite proxies `/api` to FastAPI:

```bash
# terminal 1 — API
make api            # uvicorn api.server:app --reload --port 8000

# terminal 2 — web (hot reload on http://localhost:5173)
make web            # cd web && npm install && npm run dev
```

For a production-style local run, build the SPA first so FastAPI serves it:

```bash
make web-build      # cd web && npm run build  -> web/dist
make api            # now http://localhost:8000 serves the dashboard too
```
