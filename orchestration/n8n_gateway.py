# orchestration/n8n_gateway.py
"""
N8N Gateway

Encapsulates all calls to n8n webhooks:
- get_menu
- verify_phone
- place_order

Keeping this separate lets you:
- Swap out n8n later.
- Centralize error handling and timeouts.
"""

from __future__ import annotations

from typing import Dict, Any

import httpx

from .config import settings


class N8NGateway:
    def __init__(self) -> None:
        self.menu_url = settings.N8N_MENU_WEBHOOK_URL
        self.phone_url = settings.N8N_PHONE_WEBHOOK_URL
        self.order_url = settings.N8N_ORDER_WEBHOOK_URL

    async def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not url:
            return {"error": "url_not_configured"}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                return {"raw": resp.text}

    async def get_menu(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post(self.menu_url, payload)

    async def verify_phone(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post(self.phone_url, payload)

    async def place_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post(self.order_url, payload)
