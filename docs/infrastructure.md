# Infrastructure

How the local development infrastructure works — Docker Compose, PostgreSQL, and Redis.

---

## Overview

```
Your Machine
├── .venv/             ← Python + all packages (native)
├── Django (port 8000) ← python manage.py runserver (native)
├── Celery worker      ← celery -A auto_sell worker (native)
│
└── Docker
    ├── postgres:5432  ← pgvector/pgvector:pg16
    └── redis:6379     ← redis:7-alpine (or use existing)
```

Django and Celery run natively (not in Docker) during development because:
- Code changes reload instantly without rebuilding an image
- Debugger and `print()` statements work normally
- `shell_plus` and other management commands run directly

Postgres and Redis run in Docker because setting them up natively across macOS/Linux/Windows is tedious and Docker ensures everyone has identical versions.

---

## docker-compose.yml Explained

### Default behaviour
```bash
docker compose up -d   # starts: postgres + redis only
```

The `web` and `worker` services are hidden behind the `full` profile and do **not** start by default.

### Full stack (containers only)
```bash
docker compose --profile full up   # starts: postgres + redis + web + worker
```
Use this to simulate production locally, or to run everything without activating a venv.

### Worker only
```bash
docker compose --profile worker up   # starts: postgres + redis + worker
```

---

## PostgreSQL

### Connection details (local)
| Setting | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `autosell` |
| Username | `autosell` |
| Password | `autosell` |
| Full URL | `postgres://autosell:autosell@localhost:5432/autosell` |

This matches the `DATABASE_URL` default in `.env.example`.

### Image: `pgvector/pgvector:pg16`
Standard PostgreSQL 16 with the [pgvector](https://github.com/pgvector/pgvector) extension pre-compiled and ready to use. The extension is **not enabled by default** — you need to run this once per database (already handled for the Railway production database, but not needed for FTS which is built into Postgres):

```sql
-- Only needed if/when you enable semantic search (v2)
CREATE EXTENSION IF NOT EXISTS vector;
```

For now, full-text search uses `django.contrib.postgres.search` which requires no extension.

### Data persistence
Postgres data lives in a named Docker volume (`postgres_data`). It survives `docker compose down` and `docker compose restart`.

```bash
docker compose down         # stops containers, data is preserved
docker compose down -v      # stops containers AND deletes all data (full reset)
```

### Connecting with a DB client
Any standard PostgreSQL client (TablePlus, pgAdmin, DBeaver, psql) connects at `localhost:5432` with the credentials above.

```bash
# psql (if installed on host)
psql postgres://autosell:autosell@localhost:5432/autosell

# psql inside the container
docker exec -it auto-sell-postgres-1 psql -U autosell -d autosell
```

### Migrations
Django manages the schema. Never modify the database directly — always make a migration:

```bash
python manage.py makemigrations        # create new migration files
python manage.py migrate               # apply pending migrations
python manage.py migrate --check       # exit non-zero if migrations are unapplied (use in CI)
python manage.py showmigrations        # list all migrations and their status
```

### Healthcheck
The `postgres` service has a Docker healthcheck (`pg_isready -U autosell`). The `web` and `worker` services depend on `postgres: condition: service_healthy` — they will not start until Postgres is ready to accept connections.

---

## Redis

### Connection details (local)
| Setting | Value |
|---|---|
| Host | `localhost` |
| Port | `6379` |
| Database | `0` |
| Full URL | `redis://localhost:6379/0` |

This matches the `REDIS_URL` default in `.env.example`.

### Port conflict note
The `redis` service in `docker-compose.yml` has **no host port binding** (`ports:` is omitted). This is because the development machine likely already has a Redis running on port 6379 (common on developer machines or from other Docker projects). The `REDIS_URL=redis://localhost:6379/0` in `.env` connects to whatever Redis is already running on the host.

If you need the `docker-compose.yml` Redis accessible on the host, add this to the `redis` service:
```yaml
ports:
  - "6379:6379"
```
Then stop any other Redis first: `docker stop <redis-container-name>`.

### What Redis stores

| Key pattern | Type | TTL | Contents |
|---|---|---|---|
| `conversation:{uuid}:history` | List | 72 hours | JSON-serialised message dicts `[{"role": "user", "content": "..."}]` |
| `conversation:{uuid}:lock` | String | 30 seconds | `"1"` — presence of this key means a worker is processing this conversation |
| `tenant:{slug}:system_prompt_cache` | String | 1 hour | Pre-assembled system prompt base (without dynamic catalog context) |
| `celery-task-meta-*` | String | Celery default | Celery task result storage |

### Inspecting Redis manually
```bash
# Via redis-cli (if installed)
redis-cli ping                                    # → PONG
redis-cli keys "conversation:*"                  # list all conversation keys
redis-cli lrange "conversation:<uuid>:history" 0 -1   # show full history

# Via Django shell
python manage.py shell_plus --ipython
>>> from django.core.cache import cache
>>> cache.get("tenant:my-slug:system_prompt_cache")
```

### Flushing Redis
```bash
redis-cli flushdb    # clears database 0 (all conversation history and cache)
redis-cli flushall   # clears all databases (nuclear option)
```

---

## Common Infrastructure Operations

### Start everything fresh (after cloning)
```bash
docker compose up -d
python manage.py migrate
python manage.py createsuperuser
```

### Daily startup
```bash
docker compose up -d           # ensure postgres + redis are running
source .venv/bin/activate
python manage.py runserver     # terminal 1
celery -A auto_sell worker -l info --pool=solo   # terminal 2
```

### Check what's running
```bash
docker compose ps              # container status
docker compose logs postgres   # postgres logs
docker compose logs redis      # redis logs
```

### Full reset (start from scratch)
```bash
docker compose down -v         # destroy containers + volumes
docker compose up -d           # recreate
python manage.py migrate       # recreate schema
python manage.py createsuperuser
```
