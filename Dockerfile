# Multi-stage build: Node builds the static frontend, Python serves API + UI.
# Run with docker-compose.yml (adds the Ollama service and volumes).

FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build
# -> /fe/out (Next.js static export)

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /fe/out ./static
ENV STATIC_DIR=/app/static
# chroma_db/ and credentials/ resolve to /app/chroma_db and /app/credentials
# (config.BASE_DIR = parent of app/) - mount volumes there (see compose).
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
