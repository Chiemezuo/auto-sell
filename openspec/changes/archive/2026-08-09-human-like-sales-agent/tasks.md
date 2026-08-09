## 1. Foundation — LLM Abstraction + Database Migrations

- [x] 1.1 Define `LLMProvider` ABC in `apps/conversations/llm.py` with `chat(messages, tools)` and `classify(text, labels)` methods
- [x] 1.2 Implement `DeepSeekProvider` using the existing openai SDK config (backward-compatible with current `chat()` function)
- [x] 1.3 Implement `OpenAIProvider` using the openai SDK with configurable base_url and model
- [x] 1.4 Implement `AnthropicProvider` using the anthropic SDK
- [x] 1.5 Create `get_provider(tenant, tier)` factory function in `apps/conversations/llm.py`
- [x] 1.6 Add `personality` JSONField, `primary_llm_provider` CharField, `classification_llm_provider` CharField, `co_pilot_mode` CharField to Tenant model
- [x] 1.7 Add `phase` CharField (choices: greeting/discovery/recommendation/negotiation/close) to Conversation model
- [x] 1.8 Add new conversation state choices: `owner_handling`, `co_pilot_drafting`
- [x] 1.9 Add `embedding` VectorField to Product model (pgvector, 1536 dimensions for OpenAI/text-embedding-3-small or equivalent)
- [x] 1.10 Run `python manage.py makemigrations && python manage.py migrate`
- [x] 1.11 Wire up provider selection in Celery task — `process_message` uses `get_provider(tenant, "primary")`

## 2. Conversation Engine — Phases, Personality, Sentiment

- [x] 2.1 Add `conversation_phase` tracking to `process_message`: set phase based on inbound message content and previous phase
- [x] 2.2 Implement greeting phase behavior: welcome message with business name, categories overview, open-ended question (do not search catalog)
- [x] 2.3 Implement discovery phase behavior: ask 1-2 qualifying questions (budget, preferences, use case) before searching catalog
- [x] 2.4 Implement recommendation phase behavior: run search, present products with key specs and prices
- [x] 2.5 Implement phase transition logic: greeting→discovery (vague query), discovery→recommendation (specific intent), recommendation→negotiation (counter-offer), negotiation→close (purchase intent)
- [x] 2.6 Add returning-customer acknowledgment: if conversation was previously completed/abandoned and has a context_summary, include "welcome back" with previous interaction reference
- [x] 2.7 Implement Tier 1 sentiment classification: call `provider.classify()` with labels [happy, neutral, frustrated, confused, excited, hesitant] before prompt assembly
- [x] 2.8 Build per-phase prompt templates in `prompts.py`: each phase has a distinct instruction block injected into the system prompt
- [x] 2.9 Build per-sentiment prompt modifiers: frustrated→de-escalation instructions, excited→accelerate-to-close, hesitant→address-concerns, confused→clarify
- [x] 2.10 Inject personality config (tone, formality, emoji_level) into system prompt based on tenant.personality
- [x] 2.11 Update non-text message handling: image→"I see you sent a photo! 👀 I can only read text — could you describe what you're looking for?"; voice→warm acknowledgment; sticker→friendly redirect
- [x] 2.12 Update rate-limit message: replace "slow down" with warm, human-like phrasing
- [x] 2.13 Implement multi-message sequence dispatch: LLM may return a `messages: [string]` array; task sends each with configurable delay (1-3s) between sends

## 3. Smart Negotiation

- [x] 3.1 Add `sales_count` lookup to `_dispatch_tool`: before presenting a product, query recent Sale count to determine if it's a best-seller
- [x] 3.2 Inject social proof into system prompt: if product is a best-seller, the LLM is instructed to mention it naturally
- [x] 3.3 Inject scarcity into system prompt: if `stock_quantity <= 3`, instruct LLM to mention limited availability naturally
- [x] 3.4 Add price anchoring instructions: LLM starts at `asking_price`, negotiates down gradually, accepts above floor_price but pushes back first
- [x] 3.5 Add alternative product suggestion: when customer budget is below floor_price and negotiation fails, search for same-category products within budget range
- [x] 3.6 Add cross-sell/upsell instructions: when customer commits to a product, suggest complementary accessories or premium variants if they exist in catalog
- [x] 3.7 Add bundling instructions: when customer buys a primary item, search for related accessories and offer a combined discount
- [x] 3.8 Ensure floor_price confidentiality: system prompt explicitly forbids revealing floor_price; add validation in `_dispatch_tool` for `generate_payment_link` that amount is ≥ floor_price

## 4. Semantic Search (pgvector)

- [x] 4.1 Create Celery task `generate_product_embedding(product_id)`: concatenate name + description, call embedding API via provider, store on Product.embedding
- [x] 4.2 Wire `post_save` signal on Product to enqueue `generate_product_embedding` (with short delay for batching)
- [x] 4.3 Create `semantic_search(tenant_id, query_text, limit=10)` in `apps/catalog/search.py`: embed query, cosine similarity query on Product.embedding filtered by tenant, return top matches
- [x] 4.4 Create `hybrid_search(tenant_id, query_text, limit=10)` in `apps/catalog/search.py`: run FTS and semantic in parallel, merge + deduplicate results, prioritize results appearing in both
- [x] 4.5 Update `process_message` to call `hybrid_search` instead of `get_relevant_products`
- [x] 4.6 Create backfill management command: `python manage.py backfill_embeddings` to generate embeddings for all existing products
- [x] 4.7 Add HNSW index on `embedding` field for cosine similarity performance

## 5. Co-Pilot Dashboard — WebSocket + UI

- [x] 5.1 Add `daphne` and `channels` to requirements, configure `ASGI_APPLICATION` in `auto_sell/asgi.py`
- [x] 5.2 Configure Django Channels with Redis channel layer in settings
- [x] 5.3 Create `DashboardConsumer` WebSocket consumer: authenticate via session cookie, scope to tenant, handle `conversation_update` events
- [x] 5.4 Update `process_message` to publish conversation events to Redis channel layer after each message (customer or bot)
- [x] 5.5 Create dashboard view/template at `/tenant/dashboard/` (or new `apps/dashboard/` app with Ninja API + template)
- [x] 5.6 Add REST API endpoints: `GET /api/dashboard/conversations/` (active list with unread counts), `GET /api/dashboard/conversations/{id}/messages/` (message history)
- [x] 5.7 Build dashboard UI: left panel with active conversation list (customer WA ID, last message preview, state badge), right panel with selected conversation message view
- [x] 5.8 Build conversation message view: chronological scroll, customer messages (left-aligned), bot messages (right-aligned), timestamps
- [x] 5.9 Implement owner take-over: `POST /api/dashboard/conversations/{id}/take-over/` → sets state to `owner_handling`, publishes event
- [x] 5.10 Implement owner hand-back: `POST /api/dashboard/conversations/{id}/hand-back/` → sets state to `active`, publishes event
- [x] 5.11 Add take-over/hand-back buttons to dashboard UI, text input for owner reply in `owner_handling` mode
- [x] 5.12 Implement owner reply send: `POST /api/dashboard/conversations/{id}/reply/` → sends WhatsApp message via `WhatsAppClient`, saves Message(role="assistant" with owner flag)
- [x] 5.13 Update `process_message` to skip LLM processing when state is `owner_handling` or `co_pilot_drafting`
- [x] 5.14 Handle `co_pilot_drafting` state: push draft to owner dashboard via WebSocket, owner can approve/edit/reject
- [x] 5.15 Add co-pilot mode toggle per tenant (default) and per conversation (override)

## 6. Feedback Loop

- [x] 6.1 Create `BotFeedback` model
- [x] 6.2 Add `prompt_version` field to Message model
- [ ] 6.3 Add thumbs-up/down buttons to each bot message in dashboard conversation view
- [x] 6.4 Create `POST /api/dashboard/messages/{id}/feedback/` endpoint
- [ ] 6.5 In co-pilot draft mode: when owner edits a draft, store original + edited as feedback record with type "edited"
- [ ] 6.6 Add feedback icons to conversation view: previously-rated messages show thumbs-up/down indicator
- [x] 6.7 Run migrations for BotFeedback model

## 7. Post-Purchase Engagement

- [x] 7.1-7.8, 7.10 Complete (model, tasks, beat, hooks, fields, send_template, migrations)
- [ ] 7.9 Register WhatsApp message templates with Meta: day_1_check_in, day_5_feedback, day_14_reengage, day_30_winback

## 8. Testing

- [x] 8.1 Write tests for LLM provider factory: correct provider returned per tenant config, fallback behavior
- [x] 8.2 Write tests for conversation phase transitions: greeting→discovery, discovery→recommendation, recommendation→negotiation, negotiation→close
- [ ] 8.3 Write tests for sentiment-aware prompt selection: frustrated→de-escalation, excited→accelerate, hesitant→address-concerns
- [ ] 8.4 Write tests for multi-message sequence dispatch: splitting, delays, WhatsApp send calls
- [x] 8.5 Write tests for non-text message handling: image, voice, sticker each get appropriate response
- [ ] 8.6 Write tests for smart negotiation: social proof mentions (best-seller), scarcity mentions (low stock), bundling suggestions
- [ ] 8.7 Write tests for semantic search: embedding generation, cosine similarity query, hybrid merge with FTS
- [ ] 8.8 Write tests for dashboard WebSocket: connection auth, event push on new message, tenant scoping
- [x] 8.9 Write tests for co-pilot states: owner_handling skips LLM, co_pilot_drafting queues messages, take-over/hand-back transitions
- [ ] 8.10 Write tests for feedback: rating creates BotFeedback, editing stores original+edited, prompt_version tracked
- [ ] 8.11 Write tests for post-purchase follow-ups: records created on sale, dispatched on schedule, cancelled on payment
- [x] 8.12 Run full test suite: `pytest tests/ apps/ -v` — all existing 41 tests must still pass

## 9. Deployment Preparation

- [ ] 9.1 Update `docker-compose.yml`: add optional ASGI service (daphne) with `--profile full`
- [ ] 9.2 Update `Dockerfile`: ensure daphne is installed, add ASGI start command option
- [ ] 9.3 Update `auto_sell/settings/production.py`: configure ASGI, allowed hosts for WebSocket, Redis channel layer
- [ ] 9.4 Update `docs/deployment-coolify.md`: add ASGI service configuration (separate process in Coolify)
- [ ] 9.5 Enable pgvector extension if not already: `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] 9.6 Run `python manage.py backfill_embeddings` after deployment to generate embeddings for existing products
- [ ] 9.7 Register WhatsApp message templates for post-purchase follow-ups via Meta Business dashboard
- [ ] 9.8 End-to-end smoke test: customer message → phase-aware response → negotiation → payment → dashboard visibility → owner feedback → follow-up scheduled
