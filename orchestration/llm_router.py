# orchestration/llm_router.py
"""
LLM Router

This module wraps an LLM call to classify the user's intent and
extract structured data like:
- phone
- address
- items (order lines)
- notes

We keep this layer separate so you can:
- Swap models
- Change prompts
- Unit-test routing logic independently
"""

from __future__ import annotations

import json
from typing import List, Optional

from openai import OpenAI

from .config import settings
from .models import IntentData


class LLMBasedIntentRouter:
    """
    Uses OpenAI Responses API (or ChatCompletion-style) to parse user input into
    structured JSON representing:
    - intent
    - items
    - phone
    - address
    - notes
    """

    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.LLM_ROUTER_MODEL

    def route(self, user_text: str, ctx) -> IntentData:
        """
        Synchronous call to the LLM for simplicity.

        Returns an IntentData object encapsulating intent + extracted fields.
        """
        system_prompt = """
You are Blink's food ordering brain.
You ONLY handle food-related conversation for a restaurant.

Possible intents:
- get_menu        : user is asking about the menu, items, what they can order.
- provide_phone   : user is giving or confirming a phone number.
- provide_address : user is giving or confirming a delivery address.
- place_order     : user is specifying items to order.
- chitchat        : small talk or friendly banter.
- unknown         : anything that doesn't fit.

Always respond as a JSON object with keys:
- intent       (string)
- phone        (string or null)
- address      (string or null)
- items        (array of strings; each describing one ordered item)
- notes        (string or null)
- satisfaction (number or null; optional future use)
""".strip()

        # You can enrich with a bit of context if desired
        recent_messages = [m.text for m in ctx.short_term.history[-5:]]

        # Using Responses API style (adjust if using ChatCompletion instead)
        resp = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Conversation so far: {recent_messages}\n\nUser: {user_text}",
                },
            ],
        )

        # The exact shape of resp depends on SDK version.
        # We expect a single text output that is a JSON string.
        try:
            content = resp.output[0].content[0].text  # type: ignore
        except Exception:
            # Fallback: treat entire resp as unknown
            return IntentData(
                intent="unknown",
                phone=None,
                address=None,
                items=[],
                notes=None,
                satisfaction=None,
            )

        try:
            data = json.loads(content)
        except Exception:
            data = {}

        intent = str(data.get("intent", "unknown")).lower().strip()
        phone = data.get("phone")
        address = data.get("address")
        items = data.get("items") or []
        notes = data.get("notes")
        satisfaction = data.get("satisfaction")

        # Normalize items into list of strings
        if not isinstance(items, list):
            items = [str(items)]
        else:
            items = [str(i) for i in items]

        return IntentData(
            intent=intent,
            phone=str(phone) if phone else None,
            address=str(address) if address else None,
            items=items,
            notes=str(notes) if notes else None,
            satisfaction=float(satisfaction) if satisfaction is not None else None,
        )
