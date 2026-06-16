# Data Models

Every model, every field, all relationships, and the design decisions behind them.

---

## Entity Relationship Overview

```
                    ┌──────────────┐
                    │    Tenant    │ (one business / WA number)
                    └──────┬───────┘
                           │ FK (all models scope to a Tenant)
          ┌────────────────┼─────────────────────┐
          │                │                     │
   ┌──────▼──────┐  ┌──────▼──────┐   ┌──────────▼────────┐
   │  TenantUser │  │   Product   │   │   Conversation    │
   └─────────────┘  └──────┬──────┘   └──────────┬────────┘
                           │                     │
                    ┌──────▼──────┐      ┌───────▼──────┐
                    │ProductMedia │      │   Message    │
                    └─────────────┘      └──────────────┘
                                                 │
                                       ┌─────────▼──────────┐
                                       │    PaymentLink     │
                                       └─────────┬──────────┘
                                                 │ 1:1
                                       ┌─────────▼──────────┐
                                       │       Sale         │
                                       └─────────┬──────────┘
                                                 │
                                       ┌─────────▼──────────┐
                                       │  NotificationLog   │
                                       └────────────────────┘
```

---

## Cross-Cutting Patterns

**UUID primary keys** — every model uses `UUIDField(primary_key=True, default=uuid4)` instead of auto-increment integers. Reasons:
- IDs are safe to expose in URLs and API responses (no sequential guessing)
- IDs can be generated client-side before writing to the DB
- Easier to merge data across environments

**UTC timestamps** — all `DateTimeField` values are stored in UTC (`USE_TZ = True` in settings). Convert to local time at the display layer.

**Tenant scoping** — every model except `TenantUser` has a `ForeignKey` to `Tenant`. All queries should be filtered by tenant to prevent data leakage between businesses. Example pattern:
```python
# Always filter by tenant
products = Product.objects.filter(tenant=request_tenant, is_available=True)

# Never query without tenant scope in a multi-tenant context
products = Product.objects.all()  # ← dangerous
```

**`on_delete=CASCADE`** — when a `Tenant` is deleted, all its products, conversations, payments, and notifications are deleted automatically. This is intentional — a tenant's data has no meaning without the tenant.

---

## `apps/tenants`

### `Tenant`

Represents one business using the platform. Every piece of data belongs to exactly one tenant.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (PK) | Auto-generated UUID4. Never changes after creation. |
| `name` | `CharField(255)` | Display name of the business, e.g. "Ola's Boutique". |
| `slug` | `SlugField` (unique) | URL-safe identifier, e.g. `olas-boutique`. **This is used in the WhatsApp webhook URL:** `/api/webhooks/whatsapp/olas-boutique/`. Must be unique across all tenants. Auto-populated from `name` in Django Admin. |
| `wa_phone_number_id` | `CharField(64)` (unique) | From Meta's App Dashboard. Identifies which WhatsApp number to send messages from. Each tenant gets exactly one number. |
| `wa_business_account_id` | `CharField(64)` | The WhatsApp Business Account ID from Meta. Used when making certain API calls. |
| `wa_access_token` | `TextField` | The long-lived (or permanent System User) access token from Meta. Used as the `Authorization: Bearer <token>` header in all outbound WhatsApp API calls. ⚠️ **Store securely** — field-level encryption is a planned item. |
| `wa_app_secret` | `CharField(255)` | The Meta App Secret (from Meta App Dashboard → App Settings → Basic). Used to verify the `X-Hub-Signature-256` HMAC-SHA256 header on every inbound webhook `POST`. Without this check, anyone could send fake webhook payloads. |
| `wa_webhook_verify_token` | `CharField(128)` | A random string you create and register in Meta's App Dashboard. Meta sends this back in `GET` requests to verify the webhook URL is yours. Distinct from `wa_app_secret` — this is for the one-time URL verification handshake, not per-request signature checking. |
| `owner_phone` | `CharField(32)` | The business owner's personal phone number (with country code, e.g. `2348012345678`). Sale alerts are sent here via WhatsApp. |
| `owner_email` | `EmailField` | Owner's email — backup contact, not used for automated alerts in MVP. |
| `is_active` | `BooleanField` (default `True`) | Platform admins can set this to `False` to disable a business without deleting its data. Inactive tenants should not process incoming messages. |
| `created_at` | `DateTimeField` (auto) | Set once on creation, never updated. |

**Admin:** Registered with a `TenantUserInline`, `prepopulated_fields` for slug, and collapsed WhatsApp credentials fieldset (to avoid accidentally exposing tokens).

---

### `TenantUser`

Links a Django `User` account to a `Tenant`. This is separate from the `User` model because:
- The platform has two types of users: **platform admins** (Django superusers who onboard businesses) and **business users** (who manage their own catalog)
- A `TenantUser` gives a Django `User` permission to manage a specific tenant's data
- The `OneToOneField` to `User` means one Django account maps to exactly one business — a user cannot manage two businesses in MVP

| Field | Type | Notes |
|---|---|---|
| `tenant` | `ForeignKey(Tenant)` | Which business this user manages. |
| `user` | `OneToOneField(User)` | The Django auth user. `related_name="tenant_profile"` lets you do `user.tenant_profile.tenant`. |
| `created_at` | `DateTimeField` (auto) | When the user was onboarded. |

---

## `apps/catalog`

### `Product`

A single item in a business's catalog. The LLM uses products to answer customer questions and generate payment links.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (PK) | UUID4 auto-generated. |
| `tenant` | `ForeignKey(Tenant)` | Which business owns this product. `related_name="products"`. |
| `name` | `CharField(255)` | Product name, e.g. "Nike Air Max 90". Indexed in `search_vector` with weight A (highest priority). |
| `description` | `TextField` | Full product description. Passed to the LLM as context. Indexed in `search_vector` with weight B. |
| `price_min` | `DecimalField(12, 2)` | Minimum price the bot is allowed to quote. The LLM is instructed never to go below this. |
| `price_max` | `DecimalField(12, 2)` | Maximum price. The LLM starts here and can come down to `price_min` during negotiation. The payment gateway validates that `agreed_price` is within `[price_min, price_max]`. |
| `currency` | `CharField(3)` (default `"NGN"`) | ISO 4217 currency code. `NGN` = Nigerian Naira. Single currency per product in MVP. |
| `is_available` | `BooleanField` (default `True`) | Toggle availability without deleting. Unavailable products are excluded from FTS queries. |
| `search_vector` | `SearchVectorField` | PostgreSQL tsvector. Auto-updated by a `post_save` signal whenever the product is saved. GIN-indexed for fast full-text queries. |
| `created_at` | `DateTimeField` (auto) | Creation timestamp. |
| `updated_at` | `DateTimeField` (auto_now) | Updated on every save — useful for detecting stale cached prompts. |

**Why `price_min`/`price_max` instead of a single price?**
Real-world sellers rarely have fixed prices — they negotiate. The range lets the business owner define acceptable boundaries while the AI handles the negotiation naturally. A single `price` field would remove this flexibility without adding simplicity.

**`search_vector` lifecycle:**
1. Admin saves a product (new or update)
2. Django fires `post_save` signal → `update_search_vector()` in `apps/catalog/signals.py`
3. Signal runs: `Product.objects.filter(pk=instance.pk).update(search_vector=SearchVector("name", weight="A") + SearchVector("description", weight="B"))`
4. The `update()` call bypasses another `post_save` (avoids infinite loop) and directly sets the DB column
5. The GIN index on `search_vector` makes queries like `Product.objects.filter(search_vector=SearchQuery("shoes"))` fast

---

### `ProductMedia`

Images, videos, or documents attached to a product. A product can have many media files.

| Field | Type | Notes |
|---|---|---|
| `product` | `ForeignKey(Product)` | Parent product. `related_name="media"`. Deleted when product is deleted. |
| `media_type` | `CharField` | `"image"`, `"video"`, or `"document"`. Determines which WhatsApp message type to send. |
| `s3_key` | `CharField(512)` | The file path inside the R2/S3 bucket, e.g. `tenants/olas-boutique/products/abc123/photo1.jpg`. Used to generate pre-signed URLs or CDN URLs. |
| `cdn_url` | `URLField(1024)` | The public or pre-signed URL used to actually deliver the file. Sent to WhatsApp when uploading media. |
| `wa_media_id` | `CharField(128)` | **Cached WhatsApp media ID.** When a product image is first sent to a customer, it's uploaded to WhatsApp's servers which return a `media_id`. This ID is stored here and reused on all subsequent sends — avoids uploading the same file repeatedly. Blank until first send. |
| `sort_order` | `PositiveSmallIntegerField` (default `0`) | Controls display order. The `sort_order=0` media item is the "default" image shown first. |

**Ordering:** `Meta.ordering = ["sort_order"]` means `product.media.all()` always returns files in sort order.

---

## `apps/conversations`

### `Conversation`

One thread between a customer and a business over WhatsApp. There can only be **one active conversation per customer per tenant** at a time (enforced by `unique_together`).

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (PK) | Used as the key in Redis: `conversation:{id}:history`. |
| `tenant` | `ForeignKey(Tenant)` | Which business's WhatsApp number received the message. |
| `customer_wa_id` | `CharField(32)` | The customer's WhatsApp phone number (with country code, no `+`). This is what Meta sends as the `from` field in webhook payloads. |
| `state` | `CharField` | State machine — see below. |
| `context_summary` | `TextField` | Written by the LLM when a conversation ends (`completed` or `abandoned`). A short summary of what the customer wanted and what happened. Useful for analytics and re-engagement. Blank while active. |
| `created_at` | `DateTimeField` (auto) | When the first message was received. |
| `last_message_at` | `DateTimeField` (auto_now_add) | Updated on each new message via `update_fields=["last_message_at"]` in the Celery task. `auto_now` was avoided deliberately so the field can be set manually. Intended for use by a future Celery Beat periodic task that marks conversations as `abandoned` after 24h of inactivity (Phase 7). |

**State machine transitions:**

```
          receive message
[NEW] ──────────────────────► [active]
                                  │  ▲
                    LLM calls     │  │ receive message after
                generate_payment  │  │ completed/abandoned
                    _link tool    │  │ (state reset + Redis cleared)
                                  ▼  │
                         [awaiting_payment]
                            │         │
    receive message         │         │ receive message
    + link PENDING          │         │ + link expired/failed/absent
    (reminder sent,         │         │ (state reset to active;
    LLM not called)         │         │  LLM re-engages)
                            │         │
      ┌─────────────────────┘         └──────────────────────► [active] (loop)
      │
      │  Paystack charge.success webhook         24h inactivity
      │                                          (Celery Beat — Phase 7)
      ▼                                          ▼
  [completed]                               [abandoned]

  Note: Paystack charge.failed webhook → marks PaymentLink STATUS_FAILED
  and immediately resets conversation to [active] (same path as link expired).
```

**`unique_together = [("tenant", "customer_wa_id")]`** — one row per customer per tenant, ever. When a returning customer messages after a `completed` or `abandoned` conversation, `process_message` detects the terminal state, resets it to `active`, and deletes the stale Redis history and product cache before processing continues. This keeps the schema simple (no new rows, no FK changes) while giving returning customers a fresh session.

---

### `Message`

Individual messages within a conversation. Stored in the DB for audit and deduplication. Live history for LLM context is in Redis, not here.

| Field | Type | Notes |
|---|---|---|
| `conversation` | `ForeignKey(Conversation)` | Parent conversation. `related_name="messages"`. |
| `role` | `CharField` | `"user"` (customer), `"assistant"` (bot), or `"system"` (system prompt fragments, rarely written). |
| `content` | `TextField` | Full message text. For tool call responses, this contains the rendered reply sent to the customer. |
| `wa_message_id` | `CharField(128)` (indexed) | WhatsApp's unique message ID from the webhook payload (e.g. `wamid.xxx`). **Used for idempotency:** before processing an inbound message, check if `Message.objects.filter(wa_message_id=id).exists()`. If true, Meta is retrying — return 200 without processing. Blank for outbound messages. |
| `created_at` | `DateTimeField` (auto) | Message timestamp. |

**Ordering:** `Meta.ordering = ["created_at"]` — messages are always in chronological order.

**Why is live history in Redis, not here?**
Every LLM call needs the last ~20 messages to build context. A Redis List read is O(1) and ~1ms. A DB query with ordering is ~5–20ms. At conversational speed (multiple messages per minute) this adds up. Redis is the fast-path; the DB is the audit trail.

---

## `apps/payments`

### `PaymentLink`

A Paystack payment link generated when the LLM detects buy intent. One conversation can have multiple payment links (e.g., if a customer asks for a new link after one expires).

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (PK) | UUID4. |
| `conversation` | `ForeignKey(Conversation)` | Which conversation this payment is for. `related_name="payment_links"`. |
| `tenant` | `ForeignKey(Tenant)` | Denormalised for faster queries (avoids a join through Conversation). |
| `amount` | `DecimalField(12, 2)` | The agreed sale price, validated against `product.price_min`/`price_max`. |
| `currency` | `CharField(3)` (default `"NGN"`) | ISO 4217 currency code. |
| `gateway` | `CharField(32)` (default `"paystack"`) | Which payment gateway was used. Enables filtering/reporting by gateway in future. |
| `gateway_reference` | `CharField(255)` (unique) | Paystack's transaction reference. **This is the idempotency key for the payment webhook** — when Paystack calls `/api/payments/paystack/webhook/`, look up by this field. Must be unique across all time. |
| `payment_url` | `URLField` | The URL sent to the customer. Looks like `https://paystack.com/pay/xxx`. |
| `status` | `CharField` | `pending` → `paid` (or `expired`/`failed`). |
| `created_at` | `DateTimeField` (auto) | When the link was generated. |
| `paid_at` | `DateTimeField` (null, blank) | Set when the Paystack webhook confirms payment. |

**Status lifecycle:**
```
[pending] ──── Paystack charge.success webhook ────────────────► [paid]
[pending] ──── Link expires (Paystack default: 24h) ────────────► [expired]
               (set lazily: detected when next customer message arrives)
[pending] ──── Paystack charge.failed webhook ──────────────────► [failed]
               (set proactively: webhook handler marks link + resets conversation)
```

**How expiry is handled (Option A — passive detection):**

Paystack payment links expire after 24 hours by default (no configurable TTL in the API). Rather than polling Paystack for link status, expiry is detected passively:

1. When a customer messages during `awaiting_payment`, the task checks the most recent `PaymentLink.status`.
2. If `STATUS_PENDING` → the link is still active; send a reminder and return early (LLM not called).
3. If `STATUS_EXPIRED`, `STATUS_FAILED`, or no link exists → the link is no longer actionable; reset `conversation.state` to `active` and let the LLM re-engage so the customer can renegotiate.

For **failed charges** (e.g., card declined), the Paystack `charge.failed` webhook arrives immediately. The webhook handler marks the link `STATUS_FAILED` and resets the conversation to `active` proactively — no need to wait for the customer's next message.

---

### `Sale`

Created when a payment is confirmed. Immutable audit record of a completed transaction.

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (PK) | UUID4. |
| `payment_link` | `OneToOneField(PaymentLink, PROTECT)` | One sale per payment link. `PROTECT` means you cannot delete a `PaymentLink` that has a `Sale` — preserves the audit trail. |
| `tenant` | `ForeignKey(Tenant)` | Denormalised from `payment_link.tenant` for fast dashboard queries. |
| `conversation` | `ForeignKey(Conversation)` | Denormalised from `payment_link.conversation`. |
| `customer_wa_id` | `CharField(32)` | Denormalised from `conversation.customer_wa_id` for easy display in admin and alerts. |
| `amount_paid` | `DecimalField(12, 2)` | Confirmed amount from Paystack webhook — may differ slightly from `payment_link.amount` due to fees. |
| `items_snapshot` | `JSONField` | What the customer agreed to buy. Captured from the conversation context at time of payment. Example: `[{"product_id": "...", "name": "Nike Air Max 90", "quantity": 1, "price": 50000}]`. This is a snapshot — product prices may change later. |
| `gateway_payload` | `JSONField` | The complete raw JSON body of the Paystack `charge.success` webhook. Kept verbatim for dispute resolution and auditing. Never parsed further — if you need a field from it, look it up in the raw JSON. |
| `created_at` | `DateTimeField` (auto) | When the sale was recorded (= when payment was confirmed). |

**Why `PROTECT` on `payment_link`?** If a `PaymentLink` were deleted, you'd lose the link to the conversation and amount. `PROTECT` raises a `ProtectedError` if you try — forces you to be explicit about deleting financial records.

**Why denormalise `customer_wa_id` and `tenant`?** The `Sale` model is used in Django Admin list views, Celery notification tasks, and future reporting queries. Denormalising avoids two extra joins on every access.

---

## `apps/notifications`

### `NotificationLog`

Append-only record of every alert sent (or attempted) to a business owner.

| Field | Type | Notes |
|---|---|---|
| `tenant` | `ForeignKey(Tenant)` | Which business the alert was for. |
| `sale` | `ForeignKey(Sale)` | Which sale triggered this alert. |
| `channel` | `CharField` | Currently only `"whatsapp"`. Future: `"email"`, `"sms"`. |
| `status` | `CharField` | `"sent"` or `"failed"`. |
| `error` | `TextField` (blank) | If `status="failed"`, this contains the error message or exception traceback. Empty on success. |
| `sent_at` | `DateTimeField` (auto) | When the notification attempt was made. |

**Why a separate log table instead of a status field on `Sale`?** A sale might trigger multiple notification attempts (retry on failure), or multiple channels in future. A separate log table with one row per attempt is cleaner than adding columns to `Sale`.
