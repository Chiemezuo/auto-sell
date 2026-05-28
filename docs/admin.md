# Django Admin Guide

How to use the Django Admin at `http://localhost:8000/admin/` for every task the platform supports.

---

## Access

1. Start the dev server: `python manage.py runserver`
2. Open `http://localhost:8000/admin/`
3. Log in with the superuser created during setup (`python manage.py createsuperuser`)

The admin is split into five sections — one per app: **Tenants**, **Catalog**, **Conversations**, **Payments**, **Notifications**.

---

## Tenants

### Creating a Tenant (Onboarding a Business)

A Tenant represents one business on the platform. Each business gets one WhatsApp number.

1. Go to **Tenants → Tenants → Add Tenant**
2. Fill in the top section:
   - **Name** — the business display name (e.g. "Ola's Boutique")
   - **Slug** — auto-fills from Name, but you can edit it. This becomes the webhook URL path: `/api/webhooks/whatsapp/<slug>/`. Once set, **do not change it** — changing the slug breaks the webhook URL registered with Meta.
   - **Is active** — leave checked. Uncheck to disable the business without deleting data.
3. Expand the **WhatsApp Credentials** section (collapsed by default):
   - **Wa phone number id** — from Meta App Dashboard → WhatsApp → Getting Started → Phone Number ID
   - **Wa business account id** — from Meta App Dashboard → WhatsApp Business Account ID
   - **Wa access token** — the long-lived access token from Meta. Treat this like a password.
   - **Wa webhook verify token** — a random string you create (e.g. `olas-boutique-wh-token-2024`). You will enter this same value in Meta's App Dashboard when registering the webhook URL.
4. Fill in **Owner Contact**:
   - **Owner phone** — the business owner's personal WhatsApp number for sale alerts. Include country code, no `+` or spaces: `2348012345678`
   - **Owner email** — backup contact
5. In the **Tenant Users** inline at the bottom, add a Django user for the business owner (if they need admin access). Select their user from the dropdown.
6. Click **Save**.

After saving, the webhook URL for this business is:
```
https://<your-domain>/api/webhooks/whatsapp/<slug>/
```
Register this in Meta App Dashboard → WhatsApp → Configuration → Webhook, with the verify token you set in step 3.

---

### Editing a Tenant

Everything is editable except `id` (read-only UUID). Be careful with:
- **Slug** — changing it breaks the registered webhook URL
- **Wa access token** — rotating it requires updating Meta's App Dashboard token too
- **Is active** — setting to `False` stops all message processing for this business

---

### Creating a TenantUser

1. First, create a Django User: **Authentication and Authorization → Users → Add User**
2. Then, go to **Tenants → Tenant Users → Add Tenant User**
3. Select the Tenant and the User
4. Save

Alternatively, add the user inline from inside a Tenant's edit page (the **Tenant Users** section at the bottom).

---

## Catalog

### Adding a Product

1. Go to **Catalog → Products → Add Product**
2. Fill in:
   - **Tenant** — select the business this product belongs to
   - **Name** — product name (e.g. "Nike Air Max 90 White")
   - **Description** — full description. This is passed to the LLM as context, so make it detailed: include colour, size range, material, condition, etc.
   - **Price min** — lowest acceptable price (in the chosen currency)
   - **Price max** — highest price to start at
   - **Currency** — default is NGN; change if needed
   - **Is available** — checked by default; uncheck to hide from the bot without deleting
3. Save. The **Search vector** field (visible in the Metadata section, read-only) will populate automatically within a moment via the `post_save` signal.

In the **Product Media** inline section, you can attach images/videos immediately or add them later.

**Important:** The bot only quotes prices within `[price_min, price_max]`. If a customer pushes for a lower price, the bot will go down to `price_min` but no further.

---

### Adding Product Media

You can add media via the inline on the Product edit page, or directly from **Catalog → Product Medias → Add Product Media**.

| Field | What to enter |
|---|---|
| **Product** | Select the parent product |
| **Media type** | `image`, `video`, or `document` |
| **S3 key** | The file path in your R2/S3 bucket, e.g. `tenants/olas-boutique/products/air-max-90/photo1.jpg` |
| **Cdn url** | The full public URL to access the file, e.g. `https://pub-xxx.r2.dev/tenants/olas-boutique/...` |
| **Sort order** | `0` = shown first/default. Higher numbers appear later. |
| **Wa media id** | Leave blank. This gets filled in automatically the first time the image is sent to a customer via WhatsApp. |

The `cdn_url` is what gets sent to WhatsApp's servers when uploading media. The `wa_media_id` is cached after the first upload so the file isn't re-uploaded on every send.

---

### Editing / Disabling a Product

- To temporarily hide a product from the bot: uncheck **Is available**
- To change the price range: update `price_min` / `price_max` and save — the next conversation will use the new range
- To delete a product: use the Delete button. This also deletes all attached `ProductMedia` records.

---

## Conversations

The Conversations admin is **read-only** — it's for monitoring, not managing. You cannot add or delete messages from the admin.

### Reading Conversation Records

Go to **Conversations → Conversations**.

The list view shows: customer phone number, business (tenant), current state, created time, and last message time.

**State meanings:**
| State | Meaning |
|---|---|
| `active` | Customer is currently chatting; LLM is responding |
| `awaiting_payment` | Bot sent a payment link; waiting for payment |
| `completed` | Payment confirmed; business owner has been alerted |
| `abandoned` | No messages for 24h after payment link was sent (set by Celery Beat — not yet built) |

**Filtering** by tenant, state, or date range is available in the right sidebar.

### Reading Messages

Click into a conversation to see all messages in the **Messages** inline at the bottom of the page.

| Role | Meaning |
|---|---|
| `user` | Message sent by the customer |
| `assistant` | Reply generated by the LLM and sent by the bot |
| `system` | System-level messages (rare) |

The `wa_message_id` field contains WhatsApp's unique message ID — useful for debugging duplicate processing issues.

---

## Payments

### Reading Payment Links

**Payments → Payment Links** — shows all generated payment links.

Key columns: `gateway_reference` (Paystack transaction reference), `tenant`, `amount`, `status`, `created_at`, `paid_at`.

**Status progression:**
- `pending` → link was sent to customer, waiting for payment
- `paid` → Paystack confirmed payment; a `Sale` record was created
- `expired` → customer didn't pay in time (Paystack default TTL: 24h)
- `failed` → charge was attempted and failed

To investigate a payment, click the `gateway_reference` and look up the same reference in your Paystack dashboard.

### Reading Sales

**Payments → Sales** — shows confirmed sales only. A Sale is created when the Paystack `charge.success` webhook fires.

Key fields:
- **Items snapshot** — JSON showing what the customer agreed to buy. Example:
  ```json
  [{"product_id": "abc-123", "name": "Nike Air Max 90", "agreed_price": 50000}]
  ```
- **Gateway payload** — the complete raw JSON from Paystack's webhook. Everything Paystack sent, preserved verbatim. Useful for disputes.

---

## Notifications

**Notifications → Notification Logs** — shows every sale alert sent to a business owner.

| Status | Meaning |
|---|---|
| `sent` | WhatsApp message was delivered successfully |
| `failed` | Delivery failed; check the **Error** field for the exception |

If a notification failed, the **Error** field shows the exception message. Common causes:
- Invalid `owner_phone` number format
- Expired `wa_access_token` on the Tenant
- WhatsApp API rate limit exceeded

---

## Admin Tips

**Searching across models:** Use the search box at the top of list views. Fields indexed for search:
- Tenants: `name`, `slug`, `owner_email`
- Products: `name`, `description`
- Conversations: `customer_wa_id`
- Payment Links: `gateway_reference`, `conversation__customer_wa_id`

**Filtering:** The right sidebar on list views has filters for tenant, status, date ranges, etc.

**Bulk actions:** The default "Delete selected" bulk action is available on all list views. Use carefully.

**Keyboard shortcut:** Press `g` then `h` in the Django Admin to go back to the home page.
