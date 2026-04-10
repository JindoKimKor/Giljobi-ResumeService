"""
FastAPI application — Resume Analysis Service.
SPEC: API section — /ws/analyze, /health, /noc-list
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analyze import router as analyze_router
from app.api.health import router as health_router

# LLM calls can take 30-60s — increase WebSocket timeout
app = FastAPI(title="GILJOBI Resume Analysis Service")
app.state.ws_ping_interval = 60
app.state.ws_ping_timeout = 120

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(health_router)
