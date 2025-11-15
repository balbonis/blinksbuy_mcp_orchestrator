## Blink MCP Orchestrator

This service is the **brain** behind your Blink voice assistant.

It connects:
- User speech (from the listen_channel widget)
- OpenAI LLM (for intent + entity extraction)
- n8n workflows (menu, phone verification, order handling)
- POS MCP Orchestrator (placeholder handoff)
- Analytics (logged to n8n)

---

## 🧠 High-Level Flow

1. User speaks into the **listen_client widget**
2. Widget sends STT text → `/orchestrate` on this server
3. Orchestrator:
   - Loads session context from `MemoryStore`
   - Uses `LLMBasedIntentRouter` to classify:
     - `get_menu`
     - `provide_phone`
     - `provide_address`
     - `place_order`
     - `chitchat` / `unknown`
   - Calls n8n via `N8NGateway` (menu, phone, order)
   - Validates items vs menu via `MenuValidator`
   - Sends order summary to POS MCP via `POSGateway` (placeholder)
   - Sends analytics to n8n via `AnalyticsGateway`
4. Returns a natural-language reply → widget
5. Widget sends reply to ElevenLabs TTS and plays audio

---

## 📁 Project Structure

```text
mcp_orchestrator/
├─ app.py                      # FastAPI entrypoint
├─ orchestration/
│  ├─ agent_core.py            # Main orchestrator brain
│  ├─ llm_router.py            # LLM-based intent + entity extraction
│  ├─ menu_validator.py        # Fuzzy menu item validation
│  ├─ n8n_gateway.py           # All calls to n8n webhooks
│  ├─ pos_gateway.py           # Handoff to POS MCP (placeholder)
│  ├─ analytics_gateway.py     # Analytics logs to n8n
│  ├─ session_context.py       # SessionContext, state, short-term memory
│  ├─ memory_store.py          # In-memory session store
│  ├─ models.py                # Pydantic models
│  └─ config.py                # Environment-based settings
├─ requirements.txt
├─ Procfile
└─ .env.example
