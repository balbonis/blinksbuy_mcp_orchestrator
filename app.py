# app.py
"""
FastAPI entrypoint for the MCP Orchestrator.

Exposes:
- POST /orchestrate    → main text-based orchestration endpoint
- GET  /health         → simple health check

Designed to be:
- Railway-friendly (Procfile: web: gunicorn app:app ...)
- Stateless across requests (state kept in MemoryStore)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orchestration.memory_store import MemoryStore
from orchestration.session_context import SessionContext
from orchestration.agent_core import AgentCore
from orchestration.llm_router import LLMBasedIntentRouter
from orchestration.menu_validator import MenuValidator
from orchestration.n8n_gateway import N8NGateway
from orchestration.pos_gateway import POSGateway
from orchestration.analytics_gateway import AnalyticsGateway
from orchestration.models import OrchestratorRequest, OrchestratorResponse

# ---------------------------------------------------------------------------
# App & dependencies wiring
# ---------------------------------------------------------------------------

app = FastAPI(title="Blink MCP Orchestrator", version="1.0.0")

# Basic CORS policy (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared in-process singletons
memory_store = MemoryStore(ttl_minutes=60)
intent_router = LLMBasedIntentRouter()
menu_validator = MenuValidator(fuzzy_threshold=0.7)
n8n_gateway = N8NGateway()
pos_gateway = POSGateway()
analytics_gateway = AnalyticsGateway()

agent_core = AgentCore(
    memory_store=memory_store,
    intent_router=intent_router,
    menu_validator=menu_validator,
    n8n_gateway=n8n_gateway,
    pos_gateway=pos_gateway,
    analytics_gateway=analytics_gateway,
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    """
    Simple health endpoint for uptime checks.
    """
    return {"status": "ok", "service": "mcp_orchestrator"}


@app.post("/orchestrate", response_model=OrchestratorResponse)
async def orchestrate(req: OrchestratorRequest) -> OrchestratorResponse:
    """
    Main orchestration endpoint.

    The listening client (listen_channel widget) should send:
    {
      "channel": "web",
      "user_id": "some-user",
      "session_id": "some-session-or-conversation-id",
      "text": "user's message from STT"
    }
    """
    return await agent_core.handle(req)


# For local dev convenience:
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
