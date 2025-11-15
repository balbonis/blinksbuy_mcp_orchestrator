# orchestration/memory_store.py
"""
MemoryStore

A very simple in-memory store for SessionContext, keyed by
(channel, user_id, session_id).

In production, you might want to replace this with:
- Redis
- Database
- External cache

But for a single Railway instance and your current product,
this is enough.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional

from .session_context import SessionContext


class MemoryStore:
    """
    In-memory dictionary-based session store.

    Not persistent across deployments.
    """

    def __init__(self, ttl_minutes: int = 60) -> None:
        self._store: Dict[Tuple[str, str, str], SessionContext] = {}
        self.ttl = timedelta(minutes=ttl_minutes)

    def _key(self, channel: str, user_id: str, session_id: str) -> Tuple[str, str, str]:
        return (channel, user_id, session_id)

    def load(
        self, channel: str, user_id: str, session_id: str
    ) -> Optional[SessionContext]:
        """
        Load a SessionContext if it exists and is not expired, else return None.
        """
        key = self._key(channel, user_id, session_id)
        ctx = self._store.get(key)
        if ctx is None:
            return None

        now = datetime.now(timezone.utc)
        if now - ctx.session.last_seen_at > self.ttl:
            # Session expired
            self._store.pop(key, None)
            return None

        return ctx

    def save(self, ctx: SessionContext) -> None:
        """
        Save or update a SessionContext.
        """
        key = self._key(ctx.session.channel, ctx.session.user_id, ctx.session.session_id)
        self._store[key] = ctx

    def purge_expired(self) -> None:
        """
        Remove expired sessions. This can be called periodically if needed.
        """
        now = datetime.now(timezone.utc)
        to_delete = []
        for key, ctx in self._store.items():
            if now - ctx.session.last_seen_at > self.ttl:
                to_delete.append(key)
        for key in to_delete:
            self._store.pop(key, None)
