# =============================================================================
# Dockerfile — GILJOBI Resume Analysis Service
# =============================================================================
# FastAPI + Claude CLI + psycopg2
# Base: Python 3.12 slim
# Claude CLI: installed via npm (Node.js required)
# =============================================================================

FROM python:3.12-slim

# System deps — Node.js (for Claude CLI) + PostgreSQL client libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Claude CLI via npm
RUN npm install -g @anthropic-ai/claude-code

# Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code
COPY app/ /app/app/

WORKDIR /app

EXPOSE 8000

# PYTHONUNBUFFERED: print() goes to docker logs immediately (no buffering)
# --ws-ping-interval/timeout: LLM calls take 30-60s, default 20s ping causes disconnect
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-ping-interval", "60", "--ws-ping-timeout", "120", "--log-level", "info"]
