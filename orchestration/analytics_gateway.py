# orchestration/analytics_gateway.py
"""
Analytics Gateway

Sends turn-level analytics to n8n:
- session info
- intent
- user_text / reply_text
- extracted entities (items, phone, address)
- last order snapshot
- satisfaction placeholder

This enables building dashboards later.
"""

from __future__ import annotations

from typing import Any, Dict

from datetime import datetime

import httpx

from .config import settings
from .session_context import SessionContext
from .models import OrchestratorRequest, IntentData


class AnalyticsGateway:
    def __init__(self) -> None:
        self.analytics_url = settings.N8N_ANALYTICS_WEBHOOK_URL

    async def send_analytics(
        self,
        *,
        ctx: SessionContext,
        req: OrchestratorRequest,
        intent_data: IntentData,
        reply_text: str,
        timestamp: datetime,
    ) -> None:
        if not self.analytics_url:
            return

        phone = ctx.state.scratchpad.get("phone")
        address = ctx.state.scratchpad.get("address")
        last_order_id = ctx.state.scratchpad.get("last_order_id")
        last_order_items = ctx.state.scratchpad.get("last_order_items", [])
        flow = ctx.state.flow
        step = ctx.state.step

        payload: Dict[str, Any] = {
            "timestamp": timestamp.isoformat(),
            "session": {
                "session_id": ctx.session.session_id,
                "user_id": ctx.session.user_id,
                "channel": ctx.session.channel,
            },
            "turn": {
                "intent": intent_data.intent,
                "user_text": req.text,
                "reply_text": reply_text,
                "flow": flow,
                "step": step,
            },
            "extracted": {
                "items": intent_data.items,
                "notes": intent_data.notes,
                "phone": intent_data.phone or phone,
                "address": intent_data.address or address,
            },
            "order_snapshot": {
                "reference_id": last_order_id,
                "items": last_order_items,
            },
            "satisfaction": {
                "score": intent_data.satisfaction,
                "source": "llm_placeholder",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self.analytics_url, json=payload)
        except Exception:
            # Avoid any user-impacting error from analytics
            pass
