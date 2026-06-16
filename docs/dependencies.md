# Dependencies

Every package in `pyproject.toml` / `requirements.txt`, what it does, and why it was chosen.

---

## Managing Dependencies

| File | Purpose |
|---|---|
| `pyproject.toml` | Canonical source. Loose version constraints (`>=5.1`). Edit this when adding/upgrading. |
| `requirements.txt` | Pinned snapshot generated from `pyproject.toml`. Used by Docker. |
| `.venv/` | Virtual environment. Gitignored. |

**Workflow for adding a package:**
```bash
# 1. Add to pyproject.toml under [project] dependencies
# 2. Install it
uv pip install <package>
# 3. Re-pin requirements.txt
uv pip freeze > requirements.txt
# 4. Commit both files
```

**Activate the virtual environment:**
```bash
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

---

## Web Framework

### `django==6.0.5`
The core web framework. Provides:
- ORM (object-relational mapper) — Python classes map to database tables
- Migrations — tracks and applies schema changes
- Django Admin — auto-generated management UI at `/admin/`
- Authentication — `User`, sessions, permissions
- `django.contrib.postgres` — PostgreSQL-specific fields including `SearchVectorField`

Django 6 was installed because `pyproject.toml` specifies `>=5.1` and uv resolved to the latest stable release.

### `django-ninja==1.6.2`
FastAPI-style REST API layer built on top of Django. Chosen over Django REST Framework (DRF) because:
- Pydantic schemas validate and serialize request/response data with type hints — no separate `Serializer` classes
- Auto-generates OpenAPI (Swagger) docs at `/api/docs` — essential for debugging WhatsApp webhook payloads
- Async-native: webhook handlers can be `async def` without extra configuration
- Less boilerplate: a 5-line endpoint in Ninja would be 20+ lines in DRF

All API routes live under `/api/` (mounted in `auto_sell/urls.py`). The root router is in `auto_sell/api.py`; each app adds its own sub-router.

### `django-environ==0.13.0`
Reads `.env` files and maps them to `os.environ`. Powers every `env(...)` call in `auto_sell/settings/base.py`. Without this, all secrets would have to be hardcoded or set manually in the shell.

Usage pattern in settings:
```python
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")  # reads .env into os.environ

SECRET_KEY = env("SECRET_KEY")                        # required, no default
DEBUG = env.bool("DEBUG", default=False)              # typed boolean
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[]) # comma-separated → list
DATABASE_URL = env.db("DATABASE_URL")                  # parses a full DB URL
```

### `django-extensions==4.1`
Adds useful development management commands:
- `python manage.py shell_plus` — auto-imports all models into the Django shell
- `python manage.py shell_plus --ipython` — same, but uses IPython for autocomplete and syntax highlighting
- `python manage.py runserver_plus` — enhanced dev server with Werkzeug debugger

### `whitenoise==6.12.0`
Serves static files (CSS, JS for admin) directly from Django in production — no separate Nginx or CDN needed for the MVP. Inserted as the second middleware (after `SecurityMiddleware`) so it intercepts static file requests before they reach Django's view layer.

The `CompressedManifestStaticFilesStorage` backend gzips files and appends content hashes to filenames for cache-busting.

---

## Database

### `psycopg==3.3.4` (installed with `[binary]` extra)
The PostgreSQL driver that connects Django's ORM to Postgres. This is psycopg **3** (not the older psycopg2) — it's async-capable and significantly faster. The `[binary]` extra installs a pre-compiled C extension instead of requiring a local `libpq` compiler.

### Docker image: `pgvector/pgvector:pg16`
PostgreSQL 16 with the [pgvector](https://github.com/pgvector/pgvector) extension pre-installed. Used in `docker-compose.yml` as the database container. Advantages over the plain `postgres:16` image:
- `CREATE EXTENSION vector;` works immediately — no manual compilation
- Enables semantic (embedding-based) search in a future phase without changing the DB container

For this MVP, the project uses PostgreSQL's built-in **full-text search** (`SearchVectorField`, `SearchQuery`, `SearchRank` from `django.contrib.postgres`). pgvector is available when needed.

---

## Task Queue

### `celery==5.6.3`
Distributed task queue. Every operation that takes more than ~1 second runs as a Celery task:
- Processing inbound WhatsApp messages (LLM call, catalog search, reply)
- Generating payment links (Paystack API call)
- Sending owner sale alerts
- Sending payment confirmation to customers

**Why this matters for WhatsApp:** Meta's Cloud API requires an HTTP 200 response within 5 seconds or it retries the webhook. Processing with DeepSeek can take 2–10 seconds. Celery lets the webhook return 200 immediately and do the work async.

Tasks are defined in `tasks.py` files inside each app and auto-discovered by the Celery app in `auto_sell/celery.py`.

### `redis==6.4.0`
The Python Redis client. Redis is used for two completely separate purposes in this project:

1. **Celery broker** — Celery reads/writes task messages to Redis queues (`CELERY_BROKER_URL`)
2. **Celery result backend** — stores task return values (`CELERY_RESULT_BACKEND`)
3. **Conversation history** — live message threads are stored as Redis Lists during an active conversation (`conversation:{uuid}:history`), not in Postgres, because they need to be read and written on every LLM call with minimal latency
4. **Conversation lock** — a short-lived Redis key (`conversation:{uuid}:lock`, TTL 30s) prevents two Celery workers from processing two messages from the same customer simultaneously

### Celery internals (auto-installed)
- `billiard` — process pool for Celery workers
- `amqp` — AMQP protocol implementation (used by Celery's Redis transport)
- `kombu` — messaging library underlying Celery
- `vine` — async primitives used by amqp

---

## AI / LLM

### `openai==2.38.0`
The official OpenAI Python SDK. Used here **pointed at DeepSeek's API**, not OpenAI's, because DeepSeek is fully API-compatible with OpenAI's chat completions format.

```python
from openai import OpenAI

client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[...],
    tools=[...],
)
```

This approach means switching to a different provider later (GPT-4, Claude, Gemini) is a one-line change to `base_url` and `model`. No LangChain or abstraction layers — direct SDK calls are simpler to debug and cheaper to run.

**Why DeepSeek?**
- API pricing is ~10–20× cheaper than GPT-4o for equivalent quality on conversational tasks
- Supports OpenAI-compatible tool/function calling (needed for `send_product_media`, `generate_payment_link`, `escalate_to_human`)
- Model: `deepseek-chat` for standard conversations, `deepseek-reasoner` available for complex cases

---

## Storage

### `boto3==1.43.16`
Amazon Web Services SDK for Python. Used to interact with **Cloudflare R2**, which is S3-compatible. Handles:
- Uploading product images/videos from the admin or API
- Generating presigned URLs for media access
- The `s3_key` field on `ProductMedia` is the path inside the R2 bucket

Cloudflare R2 was chosen over AWS S3 because R2 has **zero egress fees** — you pay only for storage and operations, not for data downloaded. Since product images get uploaded to WhatsApp's CDN on first send (and then served from there), this saves significantly on bandwidth costs.

### `botocore==1.43.16`
Lower-level AWS client library that boto3 depends on. Not used directly.

---

## HTTP Client

### `httpx` (included transitively via openai)
Modern async HTTP client. Will be used directly by `WhatsAppClient` (to call Meta's Graph API) and the Paystack gateway (to call Paystack's REST API). Supports both sync and async usage, connection pooling, and automatic retries.

### `certifi`
Up-to-date TLS/SSL certificate bundle. Ensures HTTPS requests to Meta, DeepSeek, and Paystack work with valid certificate verification.

---

## Payments

There is **no Paystack Python SDK** in the dependencies. Paystack's API is straightforward REST — a few `httpx` calls are cleaner than a third-party wrapper. The gateway abstraction in `apps/payments/gateways/base.py` (to be built) will define the interface; `paystack.py` will implement it.

---

## Web Server

### `gunicorn==26.0.0`
WSGI server for production. Runs Django with multiple worker processes. Configuration in `Dockerfile`:
```
gunicorn auto_sell.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 60
```
- `4 workers` — handles 4 concurrent requests; adjust based on Railway instance RAM
- `60s timeout` — allows slow responses (e.g., if a Celery result is awaited synchronously — this shouldn't happen in normal flow, but it's a safety net)

---

## Dev / Test

### `pytest-django==4.12.0`
Integrates pytest with Django. Provides:
- `@pytest.mark.django_db` decorator (or `db` fixture) to allow database access in tests
- `client` fixture — a test HTTP client for making requests to Django views
- `admin_client` fixture — logged-in admin client
- `settings` fixture — override Django settings per test
- Sets `DJANGO_SETTINGS_MODULE` from `pyproject.toml` (`[tool.pytest.ini_options]`)

### `pytest-cov==7.1.0`
Code coverage plugin for pytest. Generates terminal and HTML coverage reports.

```bash
pytest apps/ --cov=apps --cov-report=term-missing
pytest apps/ --cov=apps --cov-report=html    # opens htmlcov/index.html
```

### `faker==40.19.1`
Generates realistic fake data for tests — names, emails, phone numbers, UUIDs, text. Avoids hardcoding magic strings in test fixtures.

```python
from faker import Faker
fake = Faker()

fake.name()           # "John Smith"
fake.email()          # "john@example.com"
fake.numerify("234########")  # realistic Nigerian phone number
fake.slug()           # "my-business-slug"
```

### `fakeredis==2.30.1`
In-memory Redis implementation that replaces the real Redis client in tests. Used by patching `apps.conversations.tasks._redis` so task tests run without a live Redis connection and without polluting conversation history or locks between test runs. Supports all commands used in production: `set`, `get`, `lrange`, `rpush`, `ltrim`, `expire`, `delete`.

### `ipython>=8.0`
Enhanced interactive Python shell. Used via `python manage.py shell_plus --ipython` for:
- Exploring models interactively
- Debugging ORM queries
- Testing Redis operations manually

---

## External Accounts Required

These are not packages — they are accounts and credentials you need to have set up before certain features work.

| Service | What it's for | Where to get it |
|---|---|---|
| **DeepSeek** | LLM API key for conversation AI | [platform.deepseek.com](https://platform.deepseek.com) → Account → API Keys |
| **Meta for Developers** | WhatsApp Business Cloud API | [developers.facebook.com](https://developers.facebook.com) → Create App → WhatsApp → Get Started |
| **Paystack** | Payment link generation and webhooks | [dashboard.paystack.com](https://dashboard.paystack.com) → Settings → API Keys |
| **Cloudflare R2** | Product media storage | [cloudflare.com](https://www.cloudflare.com) → R2 Object Storage → Create Bucket → API Tokens |
| **ngrok** | Expose localhost to Meta for webhook testing | [ngrok.com](https://ngrok.com) → Free account → `ngrok http 8000` |

### Meta App Setup (more detail)
1. Go to developers.facebook.com → My Apps → Create App → Business type
2. Add the **WhatsApp** product
3. Under WhatsApp → Getting Started, note your **Phone Number ID** and **WhatsApp Business Account ID**
4. Generate a **Permanent Access Token** (temporary tokens expire in 24h — use a System User token for production)
5. Under WhatsApp → Configuration, set the webhook URL to `https://<your-ngrok-url>/api/webhooks/whatsapp/<tenant-slug>/`
6. Set the **Verify Token** to whatever you put in `Tenant.wa_webhook_verify_token`
7. Subscribe to the `messages` webhook field

### Cloudflare R2 Setup (more detail)
1. Cloudflare dashboard → R2 Object Storage → Create Bucket (name: e.g. `auto-sell-media`)
2. R2 → Manage R2 API Tokens → Create API Token
3. Permissions: Object Read & Write for your specific bucket
4. Copy **Access Key ID** → `S3_ACCESS_KEY`
5. Copy **Secret Access Key** → `S3_SECRET_KEY`
6. Your endpoint URL is: `https://<account-id>.r2.cloudflarestorage.com` → `S3_ENDPOINT_URL`
7. `S3_REGION` = `auto` for R2
