# Auto-Sell MVP — Architecture & Design

## What This Is

A multi-tenant SaaS platform that automates WhatsApp-based sales for small businesses.

**The flow in plain English:**
1. A business owner signs up. An admin gives them an account and connects their WhatsApp Business number.
2. The owner uploads their product catalog — names, descriptions, price ranges, images/videos.
3. When a customer messages the business's WhatsApp number, an AI bot takes over.
4. The bot answers product questions, shares images on demand, negotiates within the owner's set price range, and sends a payment link when the customer is ready to buy.
5. When payment is confirmed, the bot notifies the business owner so they can handle delivery.

---

## Tech Stack & Why

| Layer | Choice | Why |
|---|---|---|
| **Web Framework** | Django 5 + Django Ninja | Django Admin handles all ops (onboarding users, managing businesses). Django Ninja gives a FastAPI-like API experience with Pydantic validation, async support, and auto-generated API docs at `/api/docs`. |
| **Database** | PostgreSQL 16 | Full-text search built in. pgvector extension ready for future semantic search. |
| **Cache + Message Broker** | Redis 7 | Stores live conversation history per customer (fast, no SQL overhead). Also the Celery task queue broker. |
| **Background Tasks** | Celery 5 | All LLM calls, WhatsApp sends, and payment processing happen async — the webhook must return in under 5 seconds or Meta retries. |
| **LLM** | DeepSeek Chat API | OpenAI-compatible API, significantly cheaper. No LangChain — direct SDK calls are simpler and easier to debug for MVP. |
| **WhatsApp** | Meta's WhatsApp Business Cloud API | Official, free per-conversation pricing model. |
| **Payments** | Paystack | Easy payment link generation, widely used in target market. Built behind a pluggable interface so other gateways can be added later. |
| **Media Storage** | Cloudflare R2 (via boto3) | S3-compatible API, zero egress fees — important since images get uploaded to WhatsApp's CDN anyway. |
| **Deployment** | Railway | Managed Postgres (with pgvector), managed Redis, free HTTPS (required by Meta), GitHub push-to-deploy. Starts at ~$5/mo. |
| **Package Manager** | uv | Fastest Python package manager available. |

---

## Project Structure

```
auto-sell/
├── auto_sell/               # Django project config
│   ├── settings/
│   │   ├── base.py          # shared settings
│   │   ├── local.py         # dev overrides
│   │   └── production.py    # prod overrides (Railway)
│   ├── urls.py
│   ├── celery.py            # Celery app init
│   └── api.py               # Django Ninja root router
│
├── apps/
│   ├── tenants/             # business accounts, WA credentials
│   ├── catalog/             # products, media, full-text search
│   ├── conversations/       # WhatsApp webhook, LLM processing, message history
│   ├── payments/            # payment links, sales records, Paystack
│   └── notifications/       # owner alerts when a sale is made
│
├── docker-compose.yml       # postgres + redis (default); --profile full adds web + worker
├── Dockerfile
├── pyproject.toml
├── .env.example
└── manage.py
```

---

## Data Models

### `tenants.Tenant`
One record per business on the platform.

| Field | Notes |
|---|---|
| `id` | UUID |
| `name` | Business display name |
| `slug` | URL-safe unique ID, used in the webhook path |
| `wa_phone_number_id` | From Meta dashboard |
| `wa_business_account_id` | From Meta dashboard |
| `wa_access_token` | **Encrypted at rest** (never plaintext in DB) |
| `wa_webhook_verify_token` | Random string, set when registering webhook with Meta |
| `owner_phone` | Where to send sale alerts |
| `owner_email` | Backup contact |
| `is_active` | Platform admin can disable a tenant |

### `catalog.Product`
Each product belongs to one tenant.

| Field | Notes |
|---|---|
| `id` | UUID |
| `tenant` | FK to Tenant |
| `name` | e.g. "Nike Air Max 90" |
| `description` | Full description, fed into the LLM |
| `price_min` / `price_max` | Bot never quotes outside this range |
| `currency` | Default: NGN |
| `is_available` | Toggle visibility without deleting |
| `search_vector` | Auto-updated GIN-indexed field for full-text search |

### `catalog.ProductMedia`
Images/videos linked to a product. Stored in R2.

| Field | Notes |
|---|---|
| `product` | FK to Product |
| `media_type` | image / video / document |
| `s3_key` | Path inside the R2 bucket |
| `cdn_url` | Public or pre-signed URL |
| `wa_media_id` | Cached after first upload to WhatsApp — reused on subsequent sends |
| `sort_order` | First image is the default shown |

### `conversations.Conversation`
One record per customer ↔ business thread. There can only be one active conversation per customer per tenant at a time.

| Field | Notes |
|---|---|
| `id` | UUID |
| `tenant` | FK to Tenant |
| `customer_wa_id` | Customer's WhatsApp phone number |
| `state` | `active → awaiting_payment → completed` (or `abandoned`) |
| `context_summary` | LLM-generated summary written to DB when conversation ends |

**Live message history is stored in Redis**, not the DB — fast reads for LLM context assembly. Written to DB as a summary on completion.

### `conversations.Message`
Individual messages in a conversation. Primarily used for deduplication and audit.

| Field | Notes |
|---|---|
| `conversation` | FK to Conversation |
| `role` | user / assistant / system |
| `content` | Message text |
| `wa_message_id` | WhatsApp's unique message ID — used to prevent duplicate processing |

### `payments.PaymentLink`

| Field | Notes |
|---|---|
| `id` | UUID |
| `conversation` | FK to Conversation |
| `amount` / `currency` | The agreed sale price |
| `gateway` | "paystack" (default) |
| `gateway_reference` | Paystack transaction reference (unique) |
| `payment_url` | Sent to customer via WhatsApp |
| `status` | `pending → paid` (or `expired` / `failed`) |
| `paid_at` | Set when Paystack webhook confirms payment |

### `payments.Sale`
Created only when payment is confirmed. The source of truth for a completed sale.

| Field | Notes |
|---|---|
| `payment_link` | OneToOne FK |
| `items_snapshot` | JSON — what the customer said they wanted to buy |
| `gateway_payload` | JSON — raw Paystack webhook body, kept for audit/disputes |
| `amount_paid` | Final confirmed amount |

---

## How a WhatsApp Message Gets Processed

```
Customer sends message
        ↓
Meta Platform calls:
POST /api/webhooks/whatsapp/{tenant_slug}/
        ↓
Django Ninja webhook handler:
  1. Verify X-Hub-Signature-256 (HMAC with tenant's verify token)
  2. Check: have we seen this wa_message_id before? If yes → return 200, stop.
  3. Save Message(role="user") to DB immediately
  4. Enqueue Celery task: process_message(message_id)
  5. Return HTTP 200  ← must happen in < 5 seconds
        ↓
Celery worker: process_message
  1. Acquire Redis lock on this conversation (30s TTL)
     → prevents duplicate processing if Meta retried
  2. Load last 20 messages from Redis
  3. Full-text search catalog for keywords in the message → top 5 products
  4. Build system prompt (3 parts — see LLM section below)
  5. Call DeepSeek Chat API with tool definitions
  6. Parse the response:
     - Plain text reply → send as WhatsApp text message
     - Tool call: send_product_media → send image/video via WhatsApp
     - Tool call: generate_payment_link → create Paystack link, send URL to customer
     - Tool call: escalate_to_human → flag conversation, alert owner
  7. Save assistant message to Redis history (keep last 20, drop oldest)
  8. Update conversation.last_message_at
```

---

## How the LLM Works

### Conversation History

Live history lives in Redis as a JSON list:
- Key: `conversation:{uuid}:history`
- TTL: 72 hours (reset on each message)
- Max depth: 20 messages (oldest dropped when full)

When the conversation ends, a summary is written to `Conversation.context_summary` and Redis is cleared.

### System Prompt (rebuilt on every message)

The prompt has three parts:

**Part 1 — Identity & Rules** (cached per tenant for 1 hour)
```
You are the sales assistant for [Business Name].
Your job is to help customers find the right product and complete a purchase.

Rules:
- Never quote a price outside [min]–[max] for any product.
- Never promise delivery timelines — you handle sales only.
- If asked about something not in the catalog, say you don't carry it.
- When a customer is ready to buy, call the generate_payment_link tool.
- Reply in the same language the customer writes in.
- Keep replies short — this is WhatsApp, not email.
```

**Part 2 — Catalog Context** (dynamic, from full-text search)
```json
Relevant products:
[
  {"name": "Nike Air Max 90", "price_range": "NGN 45,000–55,000", "description": "..."},
  {"name": "Adidas Ultraboost", "price_range": "NGN 50,000–65,000", "description": "..."}
]
```

**Part 3 — Tool Definitions**

Three tools are exposed to the LLM:

- `send_product_media(product_id, media_index)` — sends an image or video for a product
- `generate_payment_link(product_id, agreed_price, currency)` — creates a Paystack link and sends it to the customer
- `escalate_to_human(reason)` — flags the conversation for the business owner to take over

The LLM decides when to call these based on the conversation. "How do I pay?" or "I'll take it" should trigger `generate_payment_link`.

---

## Payment Flow

```
LLM calls generate_payment_link tool
        ↓
Celery task:
  1. Validate: agreed_price must be within product.price_min–price_max
  2. Call Paystack API: POST /transaction/initialize
     (with conversation_id + tenant_id in metadata for webhook lookup later)
  3. Save PaymentLink to DB (status=pending)
  4. Send payment URL to customer via WhatsApp
  5. Set Conversation.state = "awaiting_payment"
        ↓
Customer pays on Paystack
        ↓
Paystack calls:
POST /api/payments/paystack/webhook/
        ↓
  1. Verify X-Paystack-Signature HMAC
  2. Event is "charge.success"?
  3. Find PaymentLink by Paystack reference
  4. Update PaymentLink.status = "paid"
  5. Create Sale record (with items snapshot + raw webhook body)
  6. Set Conversation.state = "completed"
  7. Enqueue: alert_owner(sale_id)
  8. Enqueue: send_confirmation(conversation_id)
        ↓
Owner gets WhatsApp message:
"New sale! [Customer] purchased [items] for NGN [amount]. Time to arrange delivery."
        ↓
Customer gets WhatsApp message:
"Payment received! [Business] will be in touch to arrange delivery."
```

---

## Local Development Setup

```bash
# 1. Start infrastructure
docker compose up -d           # starts postgres + redis only

# 2. Install dependencies
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 3. Set up database
cp .env.example .env           # fill in your credentials
python manage.py migrate
python manage.py createsuperuser

# 4. Run everything (3 terminals)
python manage.py runserver                          # Terminal 1: Django
celery -A auto_sell worker -l info --pool=solo      # Terminal 2: Celery
ngrok http 8000                                     # Terminal 3: expose to Meta
```

Admin dashboard: `http://localhost:8000/admin/`
API docs: `http://localhost:8000/api/docs`

---

## Deployment (Railway)

Five services, one project:

| Service | What it runs |
|---|---|
| `web` | Gunicorn serving Django + Django Ninja |
| `worker` | Celery worker (handles LLM calls, WA sends, payments) |
| `beat` | Celery Beat (periodic tasks: mark abandoned conversations) |
| `postgres` | Railway managed PostgreSQL 16 with pgvector |
| `redis` | Railway managed Redis 7 |

`web` and `worker` use the same Docker image — only the start command differs. Railway provides HTTPS automatically (required by Meta for webhook registration).

---

## What's Deliberately Left Out of MVP

These will be built after real users are using the product:

- **Semantic search** — full-text search handles MVP catalogs fine. pgvector is already available when needed.
- **Voice message handling** — for now, the bot replies "please type your question" for audio messages.
- **Real-time owner dashboard** — owner gets WhatsApp alerts. A live web dashboard comes later.
- **Abandoned cart follow-ups** — re-engaging customers who went silent after receiving a payment link.
- **Multiple payment gateways** — Flutterwave, Stripe, etc. The gateway interface is ready; implementations come later.
- **LangGraph / agentic flows** — direct DeepSeek API calls are sufficient and simpler for MVP.
- **Multiple WhatsApp numbers per business** — one number per tenant for now.
