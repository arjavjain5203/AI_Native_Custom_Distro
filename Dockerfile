# ──────────────────────────────────────────────
# AI-Native Developer Operating Environment
# Container Image
# ──────────────────────────────────────────────
# Multi-stage build: installs Python deps, copies the runtime,
# and starts the AI daemon on port 8000.

FROM python:3.12-slim AS base

LABEL maintainer="Arjav Jain"
LABEL description="AI-Native Developer Operating Environment"

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependencies ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application ──
COPY ai_core/ ai_core/
COPY daemon/ daemon/
COPY agents/ agents/
COPY models/ models/
COPY memory/ memory/
COPY tools/ tools/
COPY plugins/ plugins/
COPY interfaces/ interfaces/
COPY main.py .
COPY config.yaml .
COPY permissions.json .

# ── Runtime ──
ENV AI_OS_API_HOST=0.0.0.0
ENV AI_OS_API_PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "main.py"]
