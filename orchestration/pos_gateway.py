# orchestration/pos_gateway.py
"""
POS Gateway

Placeholder bridge to a separate POS MCP Orchestrator.

We send:
- customer phone
- customer address
- confirmed items
- order reference ID

This call is intentionally "best-effort" and should NOT affect UX if it fails.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional

import httpx
from datetime import datetime, timezone

from .config import settings
from .session_context import SessionContext


class POSGateway:
    def __init__(self) -> None:
        self.pos_url = settings.POS_MCP_URL

    async def send_to_pos(
        self,
        ctx: SessionContext,
        order_id: Optional[str],
        items: List[Dict[str, Any]],
        notes: Optional[str],
    ) -> None:
        if not self.pos_url:
            # Integration not configured yet
            return

        phone = ctx.state.scratchpad.get("phone")
        address = ctx.state.scratchpad.get("address")

        payload = {
            "customer": {
                "phone": phone,
                "address": address,
            },
            "order": {
                "reference_id": order_id,
                "items": items,
                "notes": notes,
            },
            "session": {
                "session_id": ctx.session.session_id,
                "user_id": ctx.session.user_id,
                "channel": ctx.session.channel,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self.pos_url, json=payload)
        except Exception:
            # Swallow errors to avoid impacting user
            pass
