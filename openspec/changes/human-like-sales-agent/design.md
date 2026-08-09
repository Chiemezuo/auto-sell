## Context

The current system (see MVP_PLAN.md) is a single-tier architecture: one LLM call per message, direct tool dispatch, no owner visibility. This design introduces a multi-tier LLM pipeline, structured conversation phases, a real-time owner dashboard via WebSocket, and automated post-sale engagement. All changes are additive to the existing architecture — the autonomous bot behavior remains the default.

Current tech constraints: Django 6 + Django Ninja (WSGI), Celery 5 for async, Redis for message history and locks, PostgreSQL 16 with pgvector extension available, WhatsApp Business Cloud API v19.0, DeepSeek Chat API via openai SDK.

## Goals / Non-Goals

**Goals:**
- Structured conversation flow with phase tracking and personality adaptation
- Sentiment-aware prompt selection using a lightweight classification model
- Real-time owner dashboard with WebSocket streaming and intervention controls
- Owner feedback collection with context snapshots for future prompt tuning
- Semantic product search supplementing keyword FTS
- Pluggable LLM provider architecture with per-tenant configuration
- Automated post-sale follow-up sequences and abandoned cart re-engagement

**Non-Goals:**
- Fine-tuning models on owner feedback (stores data for future use only)
- Multi-language detection and translation (architecture allows it, not implemented)
- Voice message transcription (v2 backlog)
- Owner mobile app (web dashboard only, responsive design acceptable)
- Real-time typing indicators (WhatsApp API limitation, not worth the complexity for v2)
- Full CRM with customer segmentation (customer profiles are lightweight for now)

## Decisions

### Decision 1: Conversation Phase Tracking — DB Field
Store the current phase as a CharField on the Conversation model, not just in Redis. Redis is ephemeral; the phase needs to survive restarts and be visible in the dashboard without extra Redis queries.

**Rationale**: Phases are long-lived state (minutes to hours), not transient like message history. DB storage means no extra Redis key management and phases are accessible in Django Admin and dashboard queries.

**Alternatives considered**: Redis-only (lost on restart, adds complexity for dashboard reads), computed from message history (fragile, LLM-dependent).

### Decision 2: Multi-Tier LLM — Tier 1 Synchronous in Celery Task
The sentiment/intent classifier runs synchronously within the `process_message` Celery task before the primary LLM call. It uses a cheaper model (configurable per tenant) for fast classification (~200ms).

**Rationale**: The classification is a prerequisite for prompt selection, so it must complete before the generation call. Making it synchronous avoids Celery task chaining complexity. The 200ms latency is negligible compared to the 1-2s primary LLM call.

**Pipeline order**:
```
Customer message → Rate limit check → Lock acquire → 
Tier 1: classify(sentiment, intent, language) → 
Select prompt based on phase + sentiment + intent → 
FTS + Semantic search → 
Tier 3: generate response (with tools) → 
Tool dispatch → Multi-message send → Release lock
```

### Decision 3: Tenant Personality — JSONField
Store personality config as a JSONField on Tenant: `{"tone": "friendly", "formality": "casual", "emoji_level": "moderate"}`. Injected into the system prompt as a section on communication style.

**Rationale**: Schema-less for easy extension (add new personality dimensions without migrations). The prompt builder reads it and generates the appropriate instructions. No complex inheritance or template system needed at this stage.

**Alternatives considered**: Enum field with fixed options (less flexible), separate Personality model (overkill for a prompt modifier).

### Decision 4: Multi-Message Sequences — LLM Returns Array, Task Dispatches with Sleep
The LLM is instructed (via prompt) to return multiple short messages when appropriate. The response format includes an optional `messages: [string]` array. The task iterates and sends each with `asyncio.sleep()` or Celery `time.sleep()` between them.

**Rationale**: Keeps the LLM in control of what to split and how many messages. The task just iterates with delays. No complex message queuing needed.

**Alternatives considered**: Post-processing split at fixed character count (inflexible, can split mid-sentence), separate Celery task chain per message (over-engineered).

### Decision 5: WebSocket Dashboard — Django Channels with Redis Layer
Use Django Channels for WebSocket support with Redis as the channel layer. A `DashboardConsumer` handles connection auth (tenant-scoped) and pushes conversation events. Frontend uses vanilla JS or HTMX with a WebSocket shim — not a SPA framework.

**Rationale**: Django Channels is the Django-native WebSocket solution. Redis channel layer reuses existing Redis infrastructure. Vanilla JS keeps the dashboard lightweight and avoids a frontend build pipeline for v2.

**ASGI setup**: Run with Daphne or Uvicorn instead of (or alongside) Gunicorn. The webhook and REST endpoints continue to work via the ASGI-to-WSGI adapter.

**Event flow**:
```
process_message task → Redis pub/sub → DashboardConsumer → WebSocket → Browser
Owner action (take over) → WebSocket → DashboardConsumer → DB update → 
process_message task (next message) reads new state
```

### Decision 6: pgvector Integration — Embedding Field on Product, Generation in Signal
Add a `VectorField` (pgvector) to Product. Generate embeddings in a `post_save` signal using the LLM provider's embedding capability (or a dedicated embedding model). Query by converting the customer message to an embedding and doing cosine similarity search.

**Rationale**: Embedding on the model keeps search queries simple (single-table, indexed). Signal-based generation ensures embeddings stay in sync with product updates. The embedding API is called from the provider abstraction, so it works with any configured provider.

**Search merger**: Run FTS and semantic search in parallel within `apps/catalog/search.py`. Merge results, deduplicate by product ID, sort by a weighted score (FTS matches first for exact queries, semantic first for vague queries). Return top 10 combined.

### Decision 7: LLM Provider Abstraction — ABC with Factory
Define `LLMProvider` as an ABC in `apps/conversations/llm.py` with `chat()` and `classify()` methods. Concrete implementations: `DeepSeekProvider`, `OpenAIProvider`, `AnthropicProvider`. A factory function `get_provider(tenant, tier)` returns the appropriate instance.

**Configuration**: Tenant gets `primary_llm_provider` and `classification_llm_provider` CharFields (provider keys like "deepseek", "openai"). Platform default in Django settings.

**Rationale**: Simple ABC avoids pulling in langchain or other frameworks. Per-tenant fields allow different providers per tenant. Factory function centralizes provider selection logic.

**Backward compatibility**: The existing `apps/conversations/llm.py` `chat()` function becomes a thin wrapper around the provider factory with the default tenant configuration.

### Decision 8: Feedback Data Model — Separate BotFeedback Model
A new `BotFeedback` model in `apps/conversations/models.py` (or a new `apps/feedback/` app if it grows). Fields: FK to Conversation, FK to Message (the bot message), tenant FK, feedback_type (good/bad/edited), owner_note, edited_response, context_snapshot (JSON), prompt_version.

**Rationale**: Keeps feedback separate from messages for clean querying. Context snapshot captures what the bot saw when it generated the response — critical for debugging. Prompt version enables correlation analysis.

**Future use**: When enough feedback exists, a batch job can group "bad" responses by pattern and suggest prompt improvements. Owner-edited responses serve as few-shot examples.

### Decision 9: Post-Purchase Follow-Up Scheduling — PostSaleFollowUp Model + Celery Beat
A `PostSaleFollowUp` model with FK to Sale, schedule_type (day_1, day_5, day_14, day_30, cart_2h, cart_6h), scheduled_at, status (pending/sent/cancelled/failed), and message_content. Created when a Sale is completed or a PaymentLink is created (for abandoned cart).

A Celery Beat task runs every 15 minutes, finds due `PostSaleFollowUp` records, sends the WhatsApp message, and marks them as sent.

**Rationale**: The model-based approach gives visibility into what messages were sent and when. The 15-minute beat interval is a good balance between timeliness and system load. Each follow-up type has a default template that tenants can override via their `custom_instructions` or a new `follow_up_templates` JSONField.

**WhatsApp template compliance**: Messages sent outside the 24h customer service window MUST use WhatsApp message templates. The system stores template names per follow-up type. The `WhatsAppClient` is extended with `send_template(to, template_name, parameters)`.

### Decision 10: Conversation State Machine Extension
Add new states to the existing Conversation model without changing existing states:

```
Existing:  active → awaiting_payment → completed / abandoned / escalated
Added:     active → owner_handling (owner took over)
           active → co_pilot_drafting (bot drafted, waiting for owner)
           owner_handling → active (owner handed back)
           co_pilot_drafting → active (owner approved/sent draft)
           co_pilot_drafting → owner_handling (owner rejected draft)
```

The `process_message` task is updated to check these new states and skip LLM processing when in `owner_handling` or `co_pilot_drafting`.

## Risks / Trade-offs

- **[Risk] Django Channels adds deployment complexity (ASGI server, process management)**. Mitigation: start with a single Daphne process alongside the existing Gunicorn setup. Document the Coolify service configuration clearly. The ASGI server can serve both HTTP and WebSocket.
- **[Risk] pgvector embeddings increase product save latency and API costs**. Mitigation: generate embeddings in a Celery task (not synchronously in the signal), with a small delay to batch updates. Cache embeddings in Redis per query if query volume justifies it.
- **[Risk] Co-pilot draft mode adds latency to customer responses** (owner must approve before send). Mitigation: the `co_pilot_drafting` state sends an immediate "I'm checking on that for you..." acknowledgment to the customer to manage expectations.
- **[Risk] Post-purchase messages may annoy customers**. Mitigation: make all follow-ups opt-in per tenant (disabled by default). Include unsubscribe instructions in every template. Track reply rates to follow-ups.
- **[Trade-off] Two LLM calls per message increases API cost by ~25%** (classification + generation). The classification model is ~4x cheaper than the primary model, so the net cost increase is modest. The value in better prompt selection justifies it.

## Migration Plan

1. **Add DB fields and run migrations**: New fields on Tenant (personality, llm_provider, co_pilot_mode), Product (embedding), Conversation (phase, new state values). New models: BotFeedback, PostSaleFollowUp. No data migration needed — all new fields have sensible defaults.
2. **Deploy LLM abstraction and two-tier pipeline**: The refactored `llm.py` with provider ABC and factory. Existing `chat()` function preserved as backward-compatible wrapper. Classification model calls added to `process_message`.
3. **Deploy prompt overhaul**: Updated `prompts.py` with phase-aware, personality-aware, sentiment-aware prompt assembly. Update `tasks.py` for phase tracking, multi-message dispatch, warmer edge cases.
4. **Deploy semantic search**: Add embedding generation task, update `search.py` with hybrid search merger. Run backfill task to generate embeddings for existing products.
5. **Deploy dashboard and co-pilot**: Add Django Channels, ASGI config, DashboardConsumer, dashboard views/templates. New API endpoints for conversation history, take-over/hand-back, draft management.
6. **Deploy feedback and follow-ups**: BotFeedback model, dashboard feedback UI. PostSaleFollowUp model, Celery Beat task, WhatsApp template registration.

**Rollback**: All features are additive and disabled by default. Removing the ASGI server and Channels from the process list reverts the dashboard without data loss. New fields are nullable or have defaults, so reverting code does not require rollback migrations.

## Open Questions

- Which embedding model to use for pgvector? DeepSeek, OpenAI, or a dedicated embedding API like text-embedding-3-small? Depends on provider selection and cost analysis.
- Should the dashboard be a separate Django app (`apps/dashboard/`) or integrated into the existing `/tenant/` admin with custom views? Separate app is cleaner for the WebSocket consumer and templates.
- For WhatsApp templates outside the 24h window: should templates be registered per tenant or use platform-level shared templates? Platform-level is simpler for v2 but limits customization.
