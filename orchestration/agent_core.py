# orchestration/agent_core.py
"""
AgentCore

This is the main "brain" of the MCP Orchestrator.

Responsibilities:
- Maintain/consult the SessionContext (conversation state, flow, scratchpad).
- Use the LLM router to classify user intent + extract entities (items, phone, etc.).
- Call n8n workflows (menu, phone, order) via N8NGateway.
- Validate ordered items against the menu via MenuValidator.
- Send order summary to POS MCP via POSGateway (placeholder).
- Send analytics events for each turn via AnalyticsGateway.
- Return a natural-language reply + session_done flag + memory snapshot.

This module does NOT:
- Deal with HTTP / FastAPI directly (that happens in app.py).
- Deal with audio (only text).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

from .session_context import SessionContext
from .memory_store import MemoryStore
from .models import (
    OrchestratorRequest,
    OrchestratorResponse,
    MemorySnapshot,
)
from .llm_router import LLMBasedIntentRouter
from .menu_validator import MenuValidator
from .n8n_gateway import N8NGateway
from .pos_gateway import POSGateway
from .analytics_gateway import AnalyticsGateway


class AgentCore:
    """
    The core orchestrator engine.

    You typically create this once at startup and reuse it for all requests.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        intent_router: LLMBasedIntentRouter,
        menu_validator: MenuValidator,
        n8n_gateway: N8NGateway,
        pos_gateway: POSGateway,
        analytics_gateway: AnalyticsGateway,
    ) -> None:
        self.memory_store = memory_store
        self.intent_router = intent_router
        self.menu_validator = menu_validator
        self.n8n_gateway = n8n_gateway
        self.pos_gateway = pos_gateway
        self.analytics_gateway = analytics_gateway

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    async def handle(self, req: OrchestratorRequest) -> OrchestratorResponse:
        """
        Main entrypoint for a request coming from the listening client.

        Flow:
        - Load or create SessionContext from MemoryStore.
        - Append user message to short-term history.
        - Use LLM router to get intent + structured fields.
        - Route to specific handler (menu, phone, order, etc.).
        - Update context & scratchpad.
        - Send analytics event.
        - Save SessionContext back to MemoryStore.
        - Return OrchestratorResponse.
        """
        now = datetime.now(timezone.utc)

        # 1) Resolve / create session context
        ctx = self._resolve_session(req, now)

        # 2) Append user message to history
        ctx.append_user_message(text=req.text, timestamp=now)

        # 3) Use LLM to classify intent + extract entities
        intent_data = self.intent_router.route(req.text, ctx)
        intent = intent_data.intent

        # 4) Route to handler based on intent
        reply_text, session_done = await self._route_intent(
            req=req,
            ctx=ctx,
            intent_data=intent_data,
            now=now,
        )

        # Mark session done in context if needed
        ctx.state.session_done = session_done

        # 5) Build memory snapshot BEFORE we mutate anything else
        memory_snapshot = MemorySnapshot.from_ctx(ctx)

        # 6) Send analytics (non-blocking from user's POV)
        await self.analytics_gateway.send_analytics(
            ctx=ctx,
            req=req,
            intent_data=intent_data,
            reply_text=reply_text,
            timestamp=now,
        )

        # 7) Save updated context back to memory store
        self.memory_store.save(ctx)

        # 8) Build response
        return OrchestratorResponse(
            reply_text=reply_text,
            session_done=session_done,
            memory_snapshot=memory_snapshot,
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _resolve_session(self, req: OrchestratorRequest, now: datetime) -> SessionContext:
        """
        Either load an existing SessionContext from MemoryStore, or create a new one.

        Session key is typically: (channel, user_id, session_id) combined by MemoryStore.
        """
        ctx = self.memory_store.load(req.channel, req.user_id, req.session_id)
        if ctx is None:
            ctx = SessionContext.new(
                channel=req.channel,
                user_id=req.user_id,
                session_id=req.session_id,
                created_at=now,
            )
        return ctx

    async def _route_intent(
        self,
        req: OrchestratorRequest,
        ctx: SessionContext,
        intent_data,
        now: datetime,
    ) -> Tuple[str, bool]:
        """
        Switch on intent and call the appropriate handler.
        Returns:
        - reply_text
        - session_done (bool)
        """
        intent = intent_data.intent

        # Default: not done yet
        session_done = False
        reply_text: str = ""

        # Make sure flow is set (high-level scenario name)
        if ctx.state.flow is None:
            ctx.state.flow = "food_order"

        # ---------------------------------------------------------------------
        # Intent routing
        # ---------------------------------------------------------------------
        if intent == "get_menu":
            ctx.state.step = "menu"
            reply_text = await self._handle_get_menu(intent_data, ctx)

        elif intent == "provide_phone":
            ctx.state.step = "phone"
            reply_text = await self._handle_phone(intent_data, ctx)

        elif intent == "provide_address":
            ctx.state.step = "address"
            reply_text = self._handle_address(intent_data, ctx)

        elif intent == "place_order":
            ctx.state.step = "order"
            reply_text = await self._handle_order(intent_data, ctx)

        elif intent in ("chitchat", "unknown"):
            ctx.state.step = "fallback"
            reply_text = (
                "I can help you with food orders, menus, and delivery details. "
                "What would you like to eat today?"
            )

        else:
            # Safety net for any new/unknown intent
            ctx.state.step = "unknown"
            reply_text = (
                "I'm not sure I understood that. I can help you with food ordering. "
                "For example, you can say: 'Show me the menu' or 'I want a cheeseburger.'"
            )

        # For now, we only mark session_done = True explicitly when the order is clearly done.
        # We'll do that in _handle_order when appropriate.
        session_done = ctx.state.session_done
        return reply_text, session_done

    # -------------------------------------------------------------------------
    # Handlers
    # -------------------------------------------------------------------------
    async def _handle_get_menu(self, intent_data, ctx: SessionContext) -> str:
        """
        Handler: Get Menu

        Calls n8n "menu" webhook, caches menu in scratchpad, and returns
        a natural-language list of items.
        """
        payload = {
            "session_id": ctx.session.session_id,
            "user_id": ctx.session.user_id,
            "channel": ctx.session.channel,
            "intent": "get_menu",
            "notes": intent_data.notes,
        }
        data = await self.n8n_gateway.get_menu(payload)

        menu_items = data.get("menu") or data.get("items") or []
        if not menu_items:
            return (
                "Our menu system is temporarily unavailable, but I can still take your order. "
                "What would you like to eat?"
            )

        # Cache menu in scratchpad for later validation
        ctx.state.scratchpad["menu_items"] = menu_items

        lines = ["Here are some options on the menu:"]
        for item in menu_items[:10]:
            # Support dict or simple strings
            if isinstance(item, dict):
                name = item.get("name") or "Unnamed item"
                price = item.get("price")
            else:
                name = str(item)
                price = None
            if price:
                lines.append(f"- {name} — {price}")
            else:
                lines.append(f"- {name}")

        lines.append("What would you like to order?")
        return "\n".join(lines)

    async def _handle_phone(self, intent_data, ctx: SessionContext) -> str:
        """
        Handler: Provide Phone

        Uses n8n to validate/normalize phone, then stores it in scratchpad.
        """
        phone = intent_data.phone or ctx.state.scratchpad.get("phone")
        if not phone:
            return "I didn't catch your phone number. Can you say it again?"

        payload = {
            "session_id": ctx.session.session_id,
            "user_id": ctx.session.user_id,
            "intent": "provide_phone",
            "phone": phone,
        }
        data = await self.n8n_gateway.verify_phone(payload)

        verified = bool(data.get("verified", False))
        normalized = data.get("normalized_phone", phone)

        ctx.state.scratchpad["phone"] = normalized

        if verified:
            return (
                f"Got it. I’ve verified your number as {normalized}. "
                "What is your delivery address?"
            )
        return (
            f"I heard your phone as {normalized}, but I couldn’t verify it. "
            "Do you still want to use this number, or would you like to provide another one?"
        )

    def _handle_address(self, intent_data, ctx: SessionContext) -> str:
        """
        Handler: Provide Address

        For now, we just store the address in scratchpad.
        Later, you can also pass this to n8n for validation (maps, zone, etc).
        """
        address = intent_data.address or ctx.state.scratchpad.get("address")
        if not address:
            return "I didn’t catch your address. Can you please repeat it?"

        ctx.state.scratchpad["address"] = address
        return (
            f"Thanks, I have your address as: {address}. "
            "Would you like me to place the order now?"
        )

    async def _handle_order(self, intent_data, ctx: SessionContext) -> str:
        """
        Handler: Place Order

        Steps:
        - Validate ordered items against cached menu (MenuValidator).
        - If unknown items → ask user to choose from menu.
        - If valid → call n8n.order() to create/update the order.
        - Build a POS handoff payload and send to POS MCP (POSGateway).
        - Return a natural-language confirmation + ETA.
        - Optionally mark session_done = True when order is clearly finalized.
        """
        # Items extracted by LLM
        ordered_items = intent_data.items or []
        notes = intent_data.notes

        phone = ctx.state.scratchpad.get("phone")
        address = ctx.state.scratchpad.get("address")

        # 1) Validate items against menu
        valid_menu_items, unknown_items = self.menu_validator.validate_items(
            ordered_items=ordered_items,
            ctx=ctx,
        )

        if unknown_items:
            # Some items don't match the menu. Ask user to clarify.
            lines = []
            lines.append("I couldn’t find these items in our menu:")
            for itm in unknown_items:
                lines.append(f"- {itm}")

            menu_items = ctx.state.scratchpad.get("menu_items") or []
            if menu_items:
                lines.append("")
                lines.append("Here are some items you can order instead:")
                for m in menu_items[:8]:
                    if isinstance(m, dict):
                        name = m.get("name") or "Unnamed item"
                        price = m.get("price")
                    else:
                        name = str(m)
                        price = None
                    if price:
                        lines.append(f"- {name} — {price}")
                    else:
                        lines.append(f"- {name}")
            lines.append("")
            lines.append("Can you please choose from the menu items?")

            # Do NOT call n8n or POS yet
            return "\n".join(lines)

        # 2) Build payload for n8n ORDER webhook
        payload_items = valid_menu_items
        order_payload = {
            "session_id": ctx.session.session_id,
            "user_id": ctx.session.user_id,
            "intent": "place_order",
            "items": payload_items,
            "notes": notes,
            "phone": phone,
            "address": address,
        }

        data = await self.n8n_gateway.place_order(order_payload)
        order_id = data.get("order_id")
        eta = data.get("eta")

        # Store order info in scratchpad for analytics & future references
        ctx.state.scratchpad["last_order_id"] = order_id
        ctx.state.scratchpad["last_order_items"] = payload_items

        # 3) Build POS payload (handoff to POS MCP Orchestrator)
        await self.pos_gateway.send_to_pos(
            ctx=ctx,
            order_id=order_id,
            items=payload_items,
            notes=notes,
        )

        # 4) Build user-facing reply
        base = "I’ve placed your order"
        if order_id:
            base += f" with reference ID {order_id}"
        if eta:
            base += f". Estimated delivery time is {eta}."
        else:
            base += "."

        # For now, we’ll consider this a "complete" session,
        # but you could also ask if they want anything else.
        ctx.state.session_done = True

        return base + " Thank you for ordering! Enjoy your meal."
