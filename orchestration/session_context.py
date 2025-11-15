# orchestration/session_context.py
"""
SessionContext

Represents the full conversation "brain state" for a single session.

Contains:
- Session metadata (channel, user_id, session_id, timestamps).
- State (flow, step, scratchpad, session_done).
- Short-term memory (message history, turn count).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal


Role = Literal["user", "assistant", "system"]


@dataclass
class Message:
    """
    One message in the short-term history.

    We keep this minimal: who said what, and when.
    """
    role: Role
    text: str
    timestamp: datetime


@dataclass
class SessionMeta:
    """
    Identity and lifecycle of a session.
    """
    channel: str
    user_id: str
    session_id: str
    created_at: datetime
    last_seen_at: datetime


@dataclass
class SessionState:
    """
    High-level conversational state.

    flow: name of the "scenario" (e.g., "food_order").
    step: current step (e.g., "menu", "phone", "address", "order").
    scratchpad: arbitrary dict for intermediate values.
    session_done: whether the session is logically finished.
    """
    flow: Optional[str] = None
    step: Optional[str] = None
    scratchpad: Dict[str, Any] = field(default_factory=dict)
    session_done: bool = False


@dataclass
class ShortTermMemory:
    """
    Short-term memory representing the last N messages or turns.

    You can extend this with:
    - vector store references
    - summarizations
    """
    history: List[Message] = field(default_factory=list)
    turn_count: int = 0
    last_user_message_at: Optional[datetime] = None


@dataclass
class SessionContext:
    """
    Top-level object representing everything we know about this session.
    """
    session: SessionMeta
    state: SessionState
    short_term: ShortTermMemory

    # -------------------------------------------------------------------------
    # Factory
    # -------------------------------------------------------------------------
    @classmethod
    def new(
        cls,
        *,
        channel: str,
        user_id: str,
        session_id: str,
        created_at: datetime,
    ) -> "SessionContext":
        meta = SessionMeta(
            channel=channel,
            user_id=user_id,
            session_id=session_id,
            created_at=created_at,
            last_seen_at=created_at,
        )
        state = SessionState()
        short_term = ShortTermMemory()
        return cls(session=meta, state=state, short_term=short_term)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def touch(self, now: datetime) -> None:
        """
        Update last_seen timestamp.
        """
        self.session.last_seen_at = now

    def append_user_message(self, text: str, timestamp: datetime) -> None:
        """
        Add a user message to history and bump short-term counters.
        """
        msg = Message(role="user", text=text, timestamp=timestamp)
        self.short_term.history.append(msg)
        self.short_term.turn_count += 1
        self.short_term.last_user_message_at = timestamp
        self.touch(timestamp)

    def append_assistant_message(self, text: str, timestamp: datetime) -> None:
        """
        Add an assistant message to history.
        """
        msg = Message(role="assistant", text=text, timestamp=timestamp)
        self.short_term.history.append(msg)
        self.touch(timestamp)
