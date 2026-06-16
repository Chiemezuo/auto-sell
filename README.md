# auto-sell

A multi-tenant SaaS platform that automates WhatsApp-based sales for small businesses. Business owners upload a product catalog; an AI bot (powered by DeepSeek) handles customer conversations end-to-end — answering questions, sharing product images on demand, generating payment links, and alerting the owner when a sale is confirmed.

---

## Documentation

| Doc | What it covers |
|---|---|
| [Dependencies](docs/dependencies.md) | Every package explained, external accounts required (DeepSeek, Meta, Paystack, R2) |
| [Infrastructure](docs/infrastructure.md) | Docker Compose, PostgreSQL, Redis — setup and daily operations |
| [Settings](docs/settings.md) | All environment variables and Django settings explained |
| [Data Models](docs/data-models.md) | Every model, every field, relationships, and design decisions |
| [Django Admin](docs/admin.md) | How to onboard tenants, manage products, monitor conversations and sales |
| [Testing](docs/testing.md) | Running tests, current fixtures, patterns for writing new tests |

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker Desktop | Latest | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| uv | Latest | `brew install uv` |
| ngrok | Latest | `brew install ngrok` — needed only when testing WhatsApp webhooks |

---

## First-time Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd auto-sell

# 2. Start the database and Redis
docker compose up -d

# 3. Create and activate a virtual environment
uv venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 4. Install dependencies
uv pip install -r requirements.txt

# 5. Configure environment variables
cp .env.example .env
# Edit .env — fill in SECRET_KEY and any API keys you have
# (The database and Redis values already match docker-compose defaults)

# 6. Apply migrations
python manage.py migrate

# 7. Create a superuser (for Django Admin)
python manage.py createsuperuser
```

---

## Running Locally

You need three terminal windows:

```bash
# Terminal 1 — Django dev server
source .venv/bin/activate
python manage.py runserver
```

```bash
# Terminal 2 — Celery worker (handles LLM calls, WA sends, payment tasks)
source .venv/bin/activate
celery -A auto_sell worker -l info --pool=solo
# --pool=solo is required on macOS to avoid fork issues
```

```bash
# Terminal 3 — ngrok (only needed when connecting a real WhatsApp number)
ngrok http 8000
# Copy the https URL shown (e.g. https://abc123.ngrok.io)
# Set it as the webhook URL in the Meta App Dashboard:
# https://abc123.ngrok.io/api/webhooks/whatsapp/<tenant-slug>/
```

### Key URLs

| URL | What it is |
|---|---|
| `http://localhost:8000/admin/` | Django Admin — manage tenants, products, conversations, sales |
| `http://localhost:8000/api/docs` | Auto-generated API docs (Django Ninja) |

---

## Project Structure

```
auto-sell/
├── auto_sell/               # Django project config
│   ├── settings/
│   │   ├── base.py          # All shared settings
│   │   ├── local.py         # Local dev (DEBUG=True, ALLOWED_HOSTS=*)
│   │   └── production.py    # Production (Railway)
│   ├── celery.py            # Celery app — autodiscovers tasks from all apps
│   ├── api.py               # Django Ninja root router
│   └── urls.py              # Mounts /admin/ and /api/
│
├── apps/
│   ├── tenants/             # Business accounts + WhatsApp credentials
│   ├── catalog/             # Products, media, full-text search
│   ├── conversations/       # WhatsApp webhook, LLM, message history
│   ├── payments/            # Payment links, sales, Paystack
│   └── notifications/       # Owner sale alerts
│
├── docker-compose.yml       # Starts postgres (5432) + redis (internal)
├── Dockerfile               # Used for production deployment
├── pyproject.toml           # Python dependencies (managed with uv)
├── requirements.txt         # Pinned deps for Docker
└── .env.example             # Template for .env
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values below.

### Required to run at all

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key — generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DATABASE_URL` | Postgres connection string — default matches docker-compose |
| `REDIS_URL` | Redis connection string — default matches docker-compose |

### Required for WhatsApp integration

Get these from the [Meta for Developers](https://developers.facebook.com/) dashboard after creating a WhatsApp Business app.

| Variable | Description |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API key from [platform.deepseek.com](https://platform.deepseek.com/) |

Each **Tenant** in Django Admin also stores its own WhatsApp credentials (set per business after onboarding):
- `wa_phone_number_id` — from the Meta dashboard
- `wa_business_account_id` — from the Meta dashboard
- `wa_access_token` — the long-lived access token
- `wa_webhook_verify_token` — a random string you choose; must match what you set in Meta dashboard

### Required for payments

| Variable | Description |
|---|---|
| `PAYSTACK_SECRET_KEY` | From [dashboard.paystack.com](https://dashboard.paystack.com/) → Settings → API Keys |
| `PAYSTACK_PUBLIC_KEY` | Same location |

### Required for media storage

| Variable | Description |
|---|---|
| `S3_ENDPOINT_URL` | R2: `https://<account-id>.r2.cloudflarestorage.com` / AWS: leave blank |
| `S3_ACCESS_KEY` | R2 or AWS access key |
| `S3_SECRET_KEY` | R2 or AWS secret key |
| `S3_BUCKET_NAME` | Bucket name (e.g. `auto-sell-media`) |

---

## Onboarding a Business (Admin Flow)

1. Go to `http://localhost:8000/admin/`
2. Under **Tenants → Tenants**, click **Add Tenant**
3. Fill in:
   - **Name** — the business name
   - **Slug** — URL-safe ID (auto-filled); this becomes the webhook path
   - **WhatsApp credentials** — from the business's Meta App Dashboard
   - **Owner phone** — where sale alerts are sent (include country code, e.g. `2348012345678`)
4. Save. The webhook URL for this tenant is:
   ```
   https://<your-domain>/api/webhooks/whatsapp/<slug>/
   ```
5. Register this URL in the Meta App Dashboard under Webhooks, using the tenant's `wa_webhook_verify_token`.

---

## Adding Products (Business Owner Flow)

Via Django Admin (`/admin/catalog/product/`):

1. Click **Add Product**
2. Select the **Tenant** (business)
3. Fill in name, description, `price_min`, `price_max`, currency
4. Save — the `search_vector` field updates automatically
5. Add media files via the **Product Media** inline (add `s3_key` and `cdn_url` after uploading to R2)

---

## Running Tests

```bash
# All tests
pytest tests/ apps/ -v

# A specific test directory
pytest tests/conversations/ -v

# With coverage
pytest tests/ apps/ --cov=apps --cov-report=term-missing
```

---

## Common Commands

```bash
# Create a new migration after changing a model
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Open Django shell with all models auto-imported
python manage.py shell_plus --ipython

# Check for configuration errors
python manage.py check

# Collect static files (production)
python manage.py collectstatic --no-input

# Inspect running Celery tasks
celery -A auto_sell inspect active
```

---

## Deployment (Railway)

> See `MVP_PLAN.md` for the full deployment architecture.

1. Push the repo to GitHub
2. Create a new Railway project, connect the repo
3. Add a **PostgreSQL** service (Railway managed) — enable the pgvector extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
4. Add a **Redis** service (Railway managed)
5. Set all environment variables in Railway dashboard (same as `.env`, but with production values)
6. Set `DJANGO_SETTINGS_MODULE=auto_sell.settings.production`
7. Railway will build using `Dockerfile` and run `gunicorn auto_sell.wsgi:application`
8. For the Celery worker, add a second service pointing to the same repo with start command:
   ```
   celery -A auto_sell worker -l info -Q default,notifications
   ```

---

## Further Reading

- `MVP_PLAN.md` — full architecture, data models, LLM design, payment flow
- `ROADMAP.md` — phased implementation checklist
- `CLAUDE.md` — guidance for AI-assisted development
