# Django Admin Guide

There are two separate admin sites:

| URL | Who uses it | What they can do |
|---|---|---|
| `http://localhost:8000/admin/` | Platform superusers | Everything — all tenants, all data, full control |
| `http://localhost:8000/tenant/` | Business owners (TenantUsers) | Their own products, conversations, sales, and notifications only |

The two sites share nothing. A superuser cannot log in at `/tenant/` and a TenantUser cannot log in at `/admin/`.

---

## Platform Admin (`/admin/`)

### Access

1. Start the dev server: `python manage.py runserver`
2. Open `http://localhost:8000/admin/`
3. Log in with the superuser created during setup (`python manage.py createsuperuser`)

---

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
5. Click **Save**.

After saving, the webhook URL for this business is:
```
https://<your-domain>/api/webhooks/whatsapp/<slug>/
```
Register this in Meta App Dashboard → WhatsApp → Configuration → Webhook, with the verify token you set in step 3.

---

### Giving a Business Owner Dashboard Access

This is a two-step process: create a Django User for them, then link it to their Tenant.

**Step 1 — Create the Django User:**
1. Go to **Authentication and Authorization → Users → Add User**
2. Set a username and password
3. Save, then fill in their email on the next page
4. Do **not** check "Staff status" or "Superuser status" — they should only access `/tenant/`, not `/admin/`

**Step 2 — Link the user to their Tenant:**

Option A — from the Tenant page:
1. Open the tenant at **Tenants → Tenants → [their business]**
2. Scroll to the **Tenant Users** inline at the bottom
3. Select the user from the dropdown and save

Option B — directly:
1. Go to **Tenants → Tenant Users → Add Tenant User**
2. Select the Tenant and the User, save

Once linked, the business owner can log in at `http://localhost:8000/tenant/` with their username and password.

---

### Editing a Tenant

Everything is editable except `id` (read-only UUID). Be careful with:
- **Slug** — changing it breaks the registered webhook URL
- **Wa access token** — rotating it requires updating Meta's App Dashboard token too
- **Is active** — setting to `False` stops all message processing for this business

---

### Catalog (platform admin view)

Same as the tenant admin view below, but with an additional **Tenant** field so you can assign or reassign products across businesses. Useful for bulk setup when onboarding a new client.

---

### Monitoring Conversations, Payments, Notifications

The platform admin sees all records across all tenants. Use the **Tenant** filter in the right sidebar to narrow down to a specific business. Refer to the field descriptions in the Tenant Dashboard section below — the fields are identical, just unscoped.

---

## Tenant Dashboard (`/tenant/`)

### Access

1. Open `http://localhost:8000/tenant/`
2. Log in with the username and password the platform admin created for you

You will only ever see data belonging to your own business. There is no way to view or modify another business's data.

---

### Managing Products

**Products → Add Product** to add a new item to your catalog.

| Field | Notes |
|---|---|
| **Name** | Product name, e.g. "Nike Air Max 90 White" |
| **Description** | Full description passed to the AI. Be detailed — include colour, size range, material, condition, etc. The more detail, the better the bot answers customer questions. |
| **Price min** | Lowest price the bot is allowed to agree to |
| **Price max** | Starting price — the bot begins here and can come down to `price_min` if a customer negotiates |
| **Currency** | Default is NGN. Change if needed. |
| **Is available** | Uncheck to hide the product from the bot without deleting it |

The **Tenant** field does not appear — your products are automatically assigned to your business.

Save, then add images/videos in the **Product Media** section at the bottom of the page.

**Important:** The bot will never quote a price below `price_min` or above `price_max`. Set these thoughtfully.

---

### Adding Product Media

In the **Product Media** inline on the Product edit page:

| Field | What to enter |
|---|---|
| **Media type** | `image`, `video`, or `document` |
| **S3 key** | File path inside your R2/S3 bucket, e.g. `tenants/my-store/products/air-max-90/photo1.jpg` |
| **Cdn url** | Full public URL to the file, e.g. `https://pub-xxx.r2.dev/tenants/my-store/air-max-90/photo1.jpg` |
| **Sort order** | `0` = shown first. Higher numbers appear later when a customer asks for images. |
| **Wa media id** | Leave blank — filled automatically the first time the image is sent to a customer via WhatsApp |

---

### Editing / Disabling a Product

- **Hide temporarily:** uncheck **Is available** — the bot stops mentioning the product immediately
- **Change price range:** update `price_min` / `price_max` and save — takes effect on the next conversation
- **Delete:** use the Delete button — also removes all attached media records

---

### Viewing Conversations

**Conversations** — read-only list of every customer chat on your WhatsApp number.

**State meanings:**
| State | Meaning |
|---|---|
| `active` | Customer is currently chatting |
| `awaiting_payment` | Bot sent a payment link; waiting for the customer to pay |
| `completed` | Payment confirmed; you have been alerted |
| `abandoned` | No activity for 24h (handled automatically) |

Click into a conversation to read the full message thread.

---

### Viewing Sales

**Sales** — confirmed payments only. A record is created here the moment Paystack confirms a charge.

Key fields:
- **Items snapshot** — what the customer agreed to buy, recorded at the time of payment
- **Amount paid** — the final confirmed amount from Paystack

The raw Paystack webhook payload is stored internally but not shown here (visible to platform admins if needed for disputes).

---

### Viewing Notification Logs

**Notification Logs** — a record of every sale alert sent to your phone.

| Status | Meaning |
|---|---|
| `sent` | Alert was delivered to your WhatsApp |
| `failed` | Delivery failed — contact the platform admin if this keeps happening |

---

## How the Two Sites Are Kept Separate

This is handled in three places in the code:

**`apps/tenants/admin_site.py`** — defines `TenantAdminSite` with a `has_permission` override:
```python
def has_permission(self, request):
    return (
        request.user.is_active
        and not request.user.is_superuser   # superusers use /admin/
        and hasattr(request.user, "tenant_profile")  # must be a linked TenantUser
    )
```

**Each app's `admin.py`** — registers two separate admin classes: one on `admin.site` (platform), one on `tenant_admin` (business owners). The tenant versions override `get_queryset` to filter by the logged-in user's tenant:
```python
def get_queryset(self, request):
    return super().get_queryset(request).filter(
        tenant=request.user.tenant_profile.tenant
    )
```

**`auto_sell/urls.py`** — mounts the two sites at different paths:
```python
path("admin/", admin.site.urls),    # platform admins
path("tenant/", tenant_admin.urls), # business owners
```
