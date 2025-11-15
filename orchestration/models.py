
# orchestration/models.py
"""
Pydantic models for request/response and internal structures
that need to be serialized (e.g., MemorySnapshot).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OrchestratorRequest(BaseModel):
    """
    Incoming payload from the listening client (listen_channel widget).
    """
    channel: str = Field(..., description="Channel identifier, e.g. 'web'")
    user_id: str = Field(..., description="Stable user identifier")
    session_id: str = Field(..., description="Session identifier controlled by client")
    text: str = Field(..., description="User's message (from STT)")


class MemorySnapshot(BaseModel):
    """
    Lightweight snapshot of the session memory, returned for debugging or
    external analytics if desired.
    """
    flow: Optional[str]
    step: Optional[str]
    scratchpad: Dict[str, Any]
    last_user_message_at: Optional[datetime]
    turn_count: int

    @classmethod
    def from_ctx(cls, ctx) -> "MemorySnapshot":
        return cls(
            flow=ctx.state.flow,
            step=ctx.state.step,
            scratchpad=ctx.state.scratchpad,
            last_user_message_at=ctx.short_term.last_user_message_at,
            turn_count=ctx.short_term.turn_count,
        )


class OrchestratorResponse(BaseModel):
    """
    Outgoing payload to the listening client.
    """
    reply_text: str
    session_done: bool = False
    memory_snapshot: MemorySnapshot


class IntentData(BaseModel):
    """
    Result from the LLM router.

    Represents the "semantic interpretation" of the user's message.
    """
    intent: str
    phone: Optional[str] = None
    address: Optional[str] = None
    items: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    satisfaction: Optional[float] = None
