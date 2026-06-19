# Auto-Sell MVP — Implementation Roadmap

## Phase 1 — Scaffolding ✅

- [x] Create `pyproject.toml` with all dependencies (Django, Django Ninja, Celery, Redis, psycopg2, openai, boto3, pytest, etc.)
- [x] Run `uv venv .venv` and install dependencies
- [x] Scaffold Django project: `auto_sell/` package with `settings/base.py`, `settings/local.py`, `settings/production.py`
- [x] Create `auto_sell/celery.py` (Celery app init)
- [x] Create `auto_sell/api.py` (Django Ninja root router)
- [x] Create `auto_sell/urls.py` (wire Ninja router + admin)
- [x] Create `manage.py`
- [x] Create `docker-compose.yml` (postgres + redis by default; `--profile full` adds web + worker)
- [x] Create `Dockerfile`
- [x] Create `.env.example`
- [x] Create `CLAUDE.md` at project root
- [x] Initialize git repo + `.gitignore`

---

## Phase 2 — Tenants App ✅

- [x] App created at `apps/tenants/`
- [x] Create `Tenant` model (UUID PK, slug, WhatsApp credentials, owner contact, `is_active`)
- [x] Create `TenantUser` model (FK to Tenant + Django User)
- [ ] Add field-level encryption for `wa_access_token` (use `django-fernet-fields`)
- [x] Register `Tenant` and `TenantUser` in Django Admin
- [x] Write and run migrations

---

## Phase 3 — Catalog App ✅

- [x] App created at `apps/catalog/`
- [x] Create `Product` model (UUID, tenant FK, name, description, price_min, price_max, currency, is_available, `search_vector`)
- [x] Create `ProductMedia` model (product FK, media_type, s3_key, cdn_url, wa_media_id, sort_order)
- [x] Add GIN index on `search_vector`
- [x] Wire `post_save` signal to update `search_vector` on Product save
- [x] Create `apps/catalog/storage.py` — boto3 S3/R2 client, `upload_product_media()`
- [x] Create `apps/catalog/search.py` — `get_relevant_products(tenant_id, query_text, limit=5)`
- [x] Add Django Ninja endpoint for media upload (`POST /api/catalog/products/{id}/media/`)
- [x] Register Product and ProductMedia in Django Admin (with inline media)
- [x] Write and run migrations
- [ ] Write catalog tests (FTS search, search_vector signal, media upload)

---

## Phase 4 — Conversations App + WhatsApp Webhook ✅

- [x] App created at `apps/conversations/`
- [x] Create `Conversation` model (UUID, tenant FK, customer_wa_id, state, context_summary; `unique_together = (tenant, customer_wa_id)`)
- [x] Create `Message` model (conversation FK, role, content, wa_message_id)
- [x] Create `apps/conversations/whatsapp.py` — `WhatsAppClient` with `send_text()`, `send_media()`, `upload_media()`
- [x] Create `apps/conversations/llm.py` — DeepSeek client (`openai` SDK, `base_url=https://api.deepseek.com/v1`)
- [x] Create `apps/conversations/prompts.py` — system prompt assembly (3-part: rules + catalog context + tool defs)
- [x] Create Celery task `process_message`:
  - [x] Acquire Redis lock (`conversation:{uuid}:lock`, TTL 30s)
  - [x] Returning-customer re-open: reset state + clear Redis history/products cache if `completed`/`abandoned`
  - [x] Awaiting-payment guard: send reminder + return early if `awaiting_payment`
  - [x] Load/create `Conversation`; load history from Redis list
  - [x] Run FTS catalog search for inbound message terms; cache matched product IDs
  - [x] Assemble system prompt; call DeepSeek with tools
  - [x] Parse `tool_calls`: dispatch `send_product_media`, `generate_payment_link`, `escalate_to_human`
  - [x] Send reply via `WhatsAppClient`
  - [x] Append messages to Redis list (sliding window, max 20)
  - [x] Retry up to 3× on transient failures (30s delay); release lock before retry
- [x] Create Django Ninja webhook endpoint `POST /api/webhooks/whatsapp/{tenant_slug}/`:
  - [x] Verify `X-Hub-Signature-256` against `tenant.wa_app_secret`
  - [x] Idempotency check via `Message.wa_message_id`
  - [x] Non-text messages dispatch `reply_unsupported_message` task
  - [x] Persist inbound message, enqueue `process_message`, return 200
- [x] Create `reply_unsupported_message` task — sends polite "text only" reply for non-text inbound
- [x] Handle Meta webhook verification (`GET` with `hub.challenge`)
- [x] Write and run migrations
- [x] Write webhook tests (verification, deduplication, signature rejection, non-text dispatch)
- [x] Write task tests (lock, returning-customer reset, awaiting-payment guard)

---

## Phase 5 — Payments App ✅

- [x] App created at `apps/payments/`
- [x] Create `PaymentGateway` ABC in `apps/payments/gateways/base.py` (`initialize_transaction()`, `verify_webhook_signature()`)
- [x] Create `apps/payments/gateways/paystack.py` implementing the ABC
- [x] Create `PaymentLink` model (UUID, conversation FK, tenant FK, amount, currency, gateway, gateway_reference, payment_url, status, paid_at)
- [x] Create `Sale` model (OneToOne to PaymentLink, customer_wa_id, amount_paid, items_snapshot JSONField, gateway_payload JSONField)
- [x] Create Celery task `create_payment_link(conversation_id, items_snapshot, agreed_price)`:
  - [x] Call Paystack initialize transaction
  - [x] Save `PaymentLink`, send URL to customer via WA
  - [x] Set `Conversation.state = "awaiting_payment"`
- [x] Create Django Ninja endpoint `POST /api/payments/paystack/webhook/`:
  - [x] Verify `X-Paystack-Signature` HMAC-SHA512
  - [x] On `charge.success`: update `PaymentLink`, create `Sale`, update `Conversation.state = "completed"`
  - [x] On `charge.failed`: mark `PaymentLink → STATUS_FAILED`, reset `Conversation.state = "active"` (proactive expiry handling)
  - [x] Idempotency guard on `gateway_reference`
  - [x] Enqueue `alert_owner` and `send_confirmation` tasks
- [x] Register PaymentLink and Sale in Django Admin
- [x] Write and run migrations
- [x] Write Paystack webhook tests (sale creation, idempotency, signature rejection, event filtering, charge.failed handling)
- [x] Link-status guard in `process_message`: if `awaiting_payment` + link `pending` → reminder; if `expired`/`failed`/absent → reset to `active` so LLM re-engages
- [ ] Write `create_payment_link` task tests (price validation, Paystack API call, state transition)

---

## Phase 6 — Notifications App ✅

- [x] App created at `apps/notifications/`
- [x] Create `NotificationLog` model (tenant FK, sale FK, channel, status, error, sent_at)
- [x] Create Celery task `alert_owner(sale_id)`:
  - [x] Send WhatsApp message to `tenant.owner_phone` with sale summary
  - [x] Log `STATUS_SENT` to `NotificationLog` on success
  - [x] Retry up to 5× on transient failures (60s delay); log `STATUS_FAILED` only on exhaustion
- [x] Create Celery task `send_confirmation(conversation_id)`:
  - [x] Send WhatsApp confirmation to customer
- [x] Write and run migrations

---

## Phase 7 — Hardening (in progress)

- [x] Add Redis counter for per-customer rate limiting in `process_message`
- [x] Create Celery Beat periodic task: mark `Conversation.state = "abandoned"` after 24h of `last_message_at` inactivity (also sweeps `awaiting_payment` after 48h)
- [ ] Add `django-axes` or similar for admin brute-force protection
- [ ] Validate all WhatsApp payload fields with Pydantic schemas (Django Ninja)
- [ ] Add `structlog` or Django logging config for Celery task visibility
- [ ] Write `create_payment_link` task tests and catalog FTS tests

---

## Phase 8 — Deployment

- [ ] Create `railway.toml` with service definitions (web, worker, beat)
- [ ] Finalize `Dockerfile` (multi-stage, non-root user)
- [ ] Configure `auto_sell/settings/production.py` (ALLOWED_HOSTS, HTTPS, static files via WhiteNoise)
- [ ] Set all env vars in Railway dashboard
- [ ] Enable pgvector extension on Railway Postgres (`CREATE EXTENSION vector;`)
- [ ] Run `python manage.py migrate` on Railway
- [ ] Create superuser on Railway
- [ ] Register webhook URL with Meta App Dashboard
- [ ] End-to-end smoke test: send a WhatsApp message → get a catalog response → generate payment link → confirm sale → owner alert received

---

## v2 Backlog (do not build until MVP is live with users)

- [ ] pgvector semantic search for catalog
- [ ] Audio message transcription (Whisper API)
- [ ] Business owner conversation monitoring dashboard
- [ ] Abandoned cart re-engagement messages (Celery Beat)
- [ ] Flutterwave / Stripe gateway implementations
- [ ] Multi-currency per product
- [ ] LangGraph for multi-step agentic flows
- [ ] Sub-accounts / multiple WA numbers per tenant
- [ ] Field-level encryption for `wa_access_token` (Phase 2 carry-over)
