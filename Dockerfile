# Intelligent Forecast — one container: FastAPI serves the API + the built SPA.
# Stage 1: build the React app.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: the Python app.
FROM python:3.11-slim
WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code + data + the built frontend from stage 1.
COPY api/ ./api/
COPY detector/ ./detector/
COPY data/ ./data/
COPY config.py periods.py ./
COPY --from=web /web/dist ./web/dist

ENV PORT=8000
# ANTHROPIC_API_KEY is optional: set it to enable LLM-backed agent answers.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT}"]
