# Settings

All Django settings and environment variables explained.

---

## How the Settings Split Works

```
auto_sell/settings/
├── base.py        ← shared settings for all environments
├── local.py       ← overrides for local development
└── production.py  ← overrides for Railway / production
```

`local.py` and `production.py` each start with `from .base import *` — they inherit everything from `base.py` and override only what differs. Django is told which file to use via `DJANGO_SETTINGS_MODULE`.

| Where | Default value |
|---|---|
| `manage.py` | `auto_sell.settings.local` |
| `auto_sell/celery.py` | `auto_sell.settings.local` |
| `auto_sell/wsgi.py` | `auto_sell.settings.production` |
| `.env` file | Set `DJANGO_SETTINGS_MODULE=auto_sell.settings.local` (or production) |

If you run `python manage.py runserver`, it uses `local.py`. If Gunicorn uses `wsgi.py`, it uses `production.py`. You can override at any time:
```bash
DJANGO_SETTINGS_MODULE=auto_sell.settings.production python manage.py check
```

---

## How django-environ Works

`base.py` initialises an `Env` object at module load time:
```python
import environ
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")   # reads .env file into os.environ
```

After this, `env("VAR_NAME")` is equivalent to `os.environ["VAR_NAME"]` but with type casting and defaults:

```python
env("SECRET_KEY")                  # string, required — raises ImproperlyConfigured if missing
env.bool("DEBUG", default=False)   # casts "True"/"False" strings to Python bool
env.list("ALLOWED_HOSTS", default=[])   # "a,b,c" → ["a", "b", "c"]
env.db("DATABASE_URL")             # parses a full DB URL into Django DATABASES dict
```

---

## Environment Variables Reference

Copy `.env.example` to `.env` and fill these in.

### Django Core

| Variable | Type | Default | Required? | Notes |
|---|---|---|---|---|
| `SECRET_KEY` | string | — | **Yes** | Used for cryptographic signing (sessions, CSRF tokens). Generate with: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DEBUG` | bool | `False` | No | Set `True` for local dev. Never `True` in production. |
| `ALLOWED_HOSTS` | list | `[]` | In production | Comma-separated: `myapp.up.railway.app,myapp.com`. In `local.py` this is overridden to `["*"]`. |
| `DJANGO_SETTINGS_MODULE` | string | — | No | Explicitly set in `.env` to ensure Celery uses the right settings too. |

### Database

| Variable | Type | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | URL | `postgres://autosell:autosell@localhost:5432/autosell` | Full Postgres URL. `django-environ` parses this into `DATABASES["default"]`. Railway auto-injects `DATABASE_URL` when you attach a Postgres service. |

### Redis

| Variable | Type | Default | Notes |
|---|---|---|---|
| `REDIS_URL` | URL | `redis://localhost:6379/0` | Used for both the Django cache and Celery broker/result backend. Railway auto-injects `REDIS_URL`. |

### DeepSeek

| Variable | Type | Required? | Notes |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | string | For LLM features | Get from platform.deepseek.com. Looks like `sk-xxxx`. |

### Paystack

| Variable | Type | Required? | Notes |
|---|---|---|---|
| `PAYSTACK_SECRET_KEY` | string | For payments | `sk_test_xxx` for testing, `sk_live_xxx` for production. |
| `PAYSTACK_PUBLIC_KEY` | string | For payments | `pk_test_xxx` for testing. Used in frontend/embed contexts if needed. |

### Cloudflare R2 / S3

| Variable | Type | Default | Notes |
|---|---|---|---|
| `S3_ENDPOINT_URL` | URL | `""` | R2: `https://<account-id>.r2.cloudflarestorage.com`. AWS S3: leave blank (boto3 uses default endpoint). |
| `S3_ACCESS_KEY` | string | `""` | R2 or AWS Access Key ID. |
| `S3_SECRET_KEY` | string | `""` | R2 or AWS Secret Access Key. |
| `S3_BUCKET_NAME` | string | `auto-sell-media` | The bucket name in R2 or S3. |
| `S3_REGION` | string | `auto` | `auto` for R2. AWS region (e.g. `us-east-1`) for S3. |

---

## Settings Explained: `base.py`

### `INSTALLED_APPS`
```python
INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",           # /admin/ interface
    "django.contrib.auth",            # User, Group, permissions
    "django.contrib.contenttypes",    # polymorphic relations (used by admin + auth)
    "django.contrib.sessions",        # session framework
    "django.contrib.messages",        # one-time flash messages (used by admin)
    "django.contrib.staticfiles",     # static file serving
    "django.contrib.postgres",        # SearchVectorField, ArrayField, etc.
    # Third-party
    "django_extensions",              # shell_plus, runserver_plus
    # Local apps
    "apps.tenants",
    "apps.catalog",
    "apps.conversations",
    "apps.payments",
    "apps.notifications",
]
```

`django.contrib.postgres` is required for `SearchVectorField` (used in `catalog.Product`) and `GinIndex`. Without it, the catalog migrations will fail.

### `MIDDLEWARE`
Order matters. Key entries:
- `SecurityMiddleware` — HTTPS redirects, HSTS headers (first, so security applies to everything)
- `WhiteNoiseMiddleware` — serves static files before hitting Django's view layer (second)
- `SessionMiddleware` — must be before `AuthenticationMiddleware`
- `CsrfViewMiddleware` — CSRF protection for POST requests (Django Ninja bypasses this for API endpoints by default)
- `AuthenticationMiddleware` — attaches `request.user`

### `DATABASES`
```python
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://autosell:autosell@localhost:5432/autosell")
}
```
`env.db()` parses a URL like `postgres://user:pass@host:port/dbname` into the dict format Django's ORM expects.

### `CACHES`
```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
    }
}
```
Django's cache framework is used for tenant system prompt caching (`cache.set("tenant:{slug}:system_prompt_cache", ...)`) and general app-level caching.

### Celery Settings
```python
CELERY_BROKER_URL = env("REDIS_URL", ...)      # where Celery sends/receives tasks
CELERY_RESULT_BACKEND = env("REDIS_URL", ...)  # where task results are stored
CELERY_ACCEPT_CONTENT = ["json"]               # only JSON-serialized tasks
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"                        # all task schedules in UTC
```
All tasks use JSON serialization (not pickle) for security — pickle can execute arbitrary code if the Redis instance is compromised.

### Third-Party Service Settings
```python
# DeepSeek / OpenAI-compatible
DEEPSEEK_API_KEY = env("DEEPSEEK_API_KEY", default="")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"   # hardcoded, not in .env
DEEPSEEK_MODEL = "deepseek-chat"                     # hardcoded

# Paystack
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", default="")

DEFAULT_PAYMENT_GATEWAY = "paystack"   # selects which gateway class to instantiate

# S3 / R2
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default="")
S3_SECRET_KEY = env("S3_SECRET_KEY", default="")
S3_BUCKET_NAME = env("S3_BUCKET_NAME", default="")
S3_REGION = env("S3_REGION", default="auto")
```

`DEEPSEEK_BASE_URL` and `DEEPSEEK_MODEL` are hardcoded because they're not environment-specific — if you want to use a different model, change it in code.

### Static Files
```python
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```
`STATIC_ROOT` is where `python manage.py collectstatic` copies files to. WhiteNoise serves them from there. The `CompressedManifestStaticFilesStorage` backend gzips files and appends content hashes (e.g. `admin.css?v=abc123`) for cache-busting.

### `DEFAULT_AUTO_FIELD`
```python
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```
Sets the default primary key type to `BigAutoField` (64-bit integer auto-increment) for models that don't specify a primary key. All five apps' models use UUID PKs explicitly, so this only affects Django's own models (sessions, admin log, etc.).

---

## `local.py`

```python
from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

try:
    SECRET_KEY = env("SECRET_KEY")
except Exception:
    SECRET_KEY = "local-dev-secret-key-do-not-use-in-production"
```

- `DEBUG = True` enables the Django debug toolbar, detailed error pages, and auto-reload on code changes
- `ALLOWED_HOSTS = ["*"]` accepts requests from any host — safe for localhost, dangerous in production
- The `try/except` on `SECRET_KEY` means the dev server starts even if `.env` doesn't have `SECRET_KEY` set (uses a fallback)

---

## `production.py`

```python
from .base import *

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

- `SECURE_PROXY_SSL_HEADER` — tells Django that Railway's load balancer sets `X-Forwarded-Proto: https`, so Django treats requests as HTTPS even though the internal connection is HTTP
- `SECURE_SSL_REDIRECT = True` — redirects all HTTP requests to HTTPS (Railway provides HTTPS on `*.up.railway.app` automatically)
- `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` — cookies are only sent over HTTPS connections

**Note:** `ALLOWED_HOSTS` must be set in the production `.env` — it has no default and an empty list will cause Django to reject all requests with a 400 error.
