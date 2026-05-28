# Auto-Sell MVP — Implementation Roadmap

## Phase 1 — Scaffolding

- [ ] Create `pyproject.toml` with all dependencies (Django, Django Ninja, Celery, Redis, psycopg2, openai, boto3, pytest, etc.)
- [ ] Run `uv venv .venv` and `uv pip install -r requirements.txt`
- [ ] Scaffold Django project: `auto_sell/` package with `settings/base.py`, `settings/local.py`, `settings/production.py`
- [ ] Create `auto_sell/celery.py` (Celery app init)
- [ ] Create `auto_sell/api.py` (Django Ninja root router)
- [ ] Create `auto_sell/urls.py` (wire Ninja router + admin)
- [ ] Create `manage.py`
- [ ] Create `docker-compose.yml` (postgres + redis by default; `--profile full` adds web + worker)
- [ ] Create `Dockerfile`
- [ ] Create `.env.example`
- [ ] Create `CLAUDE.md` at project root
- [ ] Initialize git repo + `.gitignore`

---

## Phase 2 — Tenants App

- [ ] `python manage.py startapp tenants` → move to `apps/tenants/`
- [ ] Create `Tenant` model (UUID PK, slug, WhatsApp credentials, owner contact, `is_active`)
- [ ] Create `TenantUser` model (FK to Tenant + Django User)
- [ ] Add field-level encryption for `wa_access_token` (use `django-fernet-fields`)
- [ ] Register `Tenant` and `TenantUser` in Django Admin
- [ ] Write and run migrations

---

## Phase 3 — Catalog App

- [ ] `python manage.py startapp catalog` → move to `apps/catalog/`
- [ ] Create `Product` model (UUID, tenant FK, name, description, price_min, price_max, currency, is_available, `search_vector`)
- [ ] Create `ProductMedia` model (product FK, media_type, s3_key, cdn_url, wa_media_id, sort_order)
- [ ] Add GIN index on `search_vector`
- [ ] Wire `post_save` signal to update `search_vector` on Product save
- [ ] Create `apps/catalog/storage.py` — boto3 S3/R2 client, `upload_product_media()`, `generate_presigned_url()`
- [ ] Create `apps/catalog/search.py` — `get_relevant_products(tenant_id, query_text, limit=5)`
- [ ] Add Django Ninja endpoint for media upload (`POST /api/catalog/products/{id}/media/`)
- [ ] Register Product and ProductMedia in Django Admin (with inline media)
- [ ] Write and run migrations
- [ ] Set up `pytest` + `conftest.py` + first catalog tests

---

## Phase 4 — Conversations App + WhatsApp Webhook

- [ ] `python manage.py startapp conversations` → move to `apps/conversations/`
- [ ] Create `Conversation` model (UUID, tenant FK, customer_wa_id, state, context_summary; `unique_together = (tenant, customer_wa_id)`)
- [ ] Create `Message` model (conversation FK, role, content, wa_message_id)
- [ ] Create `apps/conversations/whatsapp.py` — `WhatsAppClient` with `send_text()`, `send_media()`, `upload_media()`
- [ ] Create `apps/conversations/llm.py` — DeepSeek client (`openai` SDK, `base_url=https://api.deepseek.com/v1`)
- [ ] Create `apps/conversations/prompts.py` — system prompt assembly (3-part: rules + catalog context + tool defs)
- [ ] Create Celery task `process_message`:
  - [ ] Acquire Redis lock (`conversation:{uuid}:lock`, TTL 30s)
  - [ ] Load/create `Conversation`; load history from Redis list
  - [ ] Run FTS catalog search for inbound message terms
  - [ ] Assemble system prompt; call DeepSeek with tools
  - [ ] Parse `tool_calls`: dispatch `send_product_media`, `generate_payment_link`, `escalate_to_human`
  - [ ] Send reply via `WhatsAppClient`
  - [ ] Append assistant message to Redis list (sliding window, max 20)
- [ ] Create Django Ninja webhook endpoint `POST /api/webhooks/whatsapp/{tenant_slug}/`:
  - [ ] Verify `X-Hub-Signature-256`
  - [ ] Idempotency check via `Message.wa_message_id`
  - [ ] Persist inbound message, enqueue `process_message`, return 200
- [ ] Handle Meta webhook verification (`GET` with `hub.challenge`)
- [ ] Write and run migrations
- [ ] Write tests for prompt assembly and tool call parsing

---

## Phase 5 — Payments App

- [ ] `python manage.py startapp payments` → move to `apps/payments/`
- [ ] Create `PaymentGateway` ABC in `apps/payments/gateways/base.py` (`initialize_transaction()`, `verify_webhook_signature()`)
- [ ] Create `apps/payments/gateways/paystack.py` implementing the ABC
- [ ] Create `PaymentLink` model (UUID, conversation FK, tenant FK, amount, currency, gateway, gateway_reference, payment_url, status, paid_at)
- [ ] Create `Sale` model (OneToOne to PaymentLink, customer_wa_id, amount_paid, items_snapshot JSONField, gateway_payload JSONField)
- [ ] Create Celery task `create_payment_link(conversation_id, product_id, agreed_price)`:
  - [ ] Validate price within product range
  - [ ] Call Paystack initialize transaction
  - [ ] Save `PaymentLink`, send URL to customer via WA
  - [ ] Set `Conversation.state = "awaiting_payment"`
- [ ] Create Django Ninja endpoint `POST /api/payments/paystack/webhook/`:
  - [ ] Verify `X-Paystack-Signature` HMAC
  - [ ] On `charge.success`: update `PaymentLink`, create `Sale`, update `Conversation.state = "completed"`
  - [ ] Enqueue `alert_owner` and `send_confirmation` tasks
- [ ] Register PaymentLink and Sale in Django Admin
- [ ] Write and run migrations
- [ ] Write tests for Paystack signature verification and payment flow

---

## Phase 6 — Notifications App

- [ ] `python manage.py startapp notifications` → move to `apps/notifications/`
- [ ] Create `NotificationLog` model (tenant FK, sale FK, channel, status, sent_at)
- [ ] Create Celery task `alert_owner(sale_id)`:
  - [ ] Send WhatsApp message to `tenant.owner_phone` with sale summary
  - [ ] Log to `NotificationLog`
- [ ] Create Celery task `send_confirmation(conversation_id)`:
  - [ ] Send WhatsApp confirmation to customer
- [ ] Write and run migrations

---

## Phase 7 — Hardening

- [ ] Add Redis counter for per-customer rate limiting in `process_message`
- [ ] Create Celery Beat periodic task: mark `Conversation.state = "abandoned"` after 24h inactivity
- [ ] Add `django-axes` or similar for admin brute-force protection
- [ ] Validate all WhatsApp payload fields with Pydantic schemas (Django Ninja)
- [ ] Add `structlog` or Django logging config for Celery task visibility
- [ ] Write integration tests for the full webhook → LLM → reply flow (mock DeepSeek and WA APIs)

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
