# foundry-studio Docker image (GPU-ready).
# Builds the backend and the frontend, then serves everything from uvicorn.

# ---------- Frontend build stage ----------
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# ---------- Backend stage ----------
FROM python:3.12-slim AS backend
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FOUNDRY_STUDIO_FRONTEND_DIST=/app/frontend/dist

RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY backend/ ./backend/

RUN pip install --upgrade pip && pip install -e ".[foundry]" || pip install -e .

# Copy the built frontend.
COPY --from=frontend /build/frontend/dist ./frontend/dist

EXPOSE 8765
CMD ["python", "-m", "foundry_studio.cli", "serve"]
