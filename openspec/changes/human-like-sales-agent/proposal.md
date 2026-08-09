## Why

The current bot closes sales but does not build relationships. It jumps from "hello" to product catalog with no discovery, negotiates mechanically, and goes silent after payment. For small businesses on WhatsApp — where repeat customers and word-of-mouth drive growth — this transactional behavior caps retention and revenue. Owners also have zero visibility into bot-customer conversations, eroding trust in automation. This change transforms the bot from a vending machine into a human-like sales agent with a co-pilot dashboard that lets owners observe, intervene, and provide feedback.

## What Changes

- **Conversation engine overhaul**: The bot moves through structured phases (Greeting → Discovery → Recommendation → Negotiation → Close) with per-tenant personality configuration and sentiment-aware message routing
- **Smart negotiation**: Social proof, scarcity, bundling, anchoring, cross-sell, and alternative suggestions replace binary within-range price checking
- **Co-pilot dashboard**: Real-time WebSocket conversation streaming, owner take-over/hand-back, bot draft approval, and conversation review — all in a web dashboard at `/tenant/`
- **Feedback loop**: Owners rate bot responses (thumbs up/down) and edit them; feedback is stored with context snapshots and prompt version for future tuning
- **Semantic search**: pgvector-based product search for intent matching, replacing keyword-only FTS for vague or conceptual customer queries
- **Pluggable LLM providers**: Abstract provider interface with DeepSeek, OpenAI, and Anthropic backends; cheap model for sentiment classification, primary model for response generation
- **Post-purchase engagement**: Automated follow-up sequence after sale (delivery check-in, feedback request, re-engagement, win-back) and abandoned cart nudges within the 24h messaging window

## Capabilities

### New Capabilities
- `conversation-engine`: Structured conversation phases, per-tenant personality profiles, sentiment-aware prompt selection, warmer edge-case messaging, and multi-message dispatch with natural pacing
- `smart-negotiation`: Social proof, scarcity signals, product bundling, price anchoring, cross-sell/upsell suggestions, and alternative product recommendations during negotiation
- `co-pilot-system`: Real-time dashboard with WebSocket conversation streaming, owner intervention (take over / hand back), bot draft review and approval, conversation history viewer, and new conversation states (owner_handling, co_pilot_drafting)
- `feedback-loop`: Bot message rating (thumbs up/down), owner-edited response capture, feedback data model with context snapshots and prompt version tracking
- `semantic-search`: pgvector embeddings for products, cosine similarity intent matching, hybrid FTS+semantic merged results
- `llm-abstraction`: Pluggable LLM provider interface, multi-provider support (DeepSeek, OpenAI, Anthropic), per-tenant provider configuration, two-tier routing (classification + generation)
- `post-purchase-engagement`: Automated follow-up sequence scheduling (Day 1, 5, 14, 30), abandoned cart re-engagement within 24h messaging window

### Modified Capabilities
<!-- No existing specs to modify — this is the first major capability set. -->

## Impact

- **Code**: `apps/conversations/` (prompts.py, tasks.py, models.py, llm.py — major refactor), `apps/tenants/models.py` (new fields: personality, llm_provider, co_pilot_mode), `apps/catalog/models.py` (embedding field), new `apps/dashboard/` or integrated in `/tenant/` admin
- **Infrastructure**: Django Channels + ASGI (WebSocket), pgvector extension (already available on `pgvector/pgvector:pg16`), Redis pub/sub for real-time events
- **API**: New REST endpoints for dashboard data, WebSocket endpoint for live streaming, expanded tool definitions for the LLM
- **Breaking**: Webhook handler routes messages differently in co-pilot/owner modes — existing autonomous behavior is preserved as the default, so no breaking changes to the inbound path. Conversation state enum gains new values (owner_handling, co_pilot_drafting) but existing states remain unchanged
