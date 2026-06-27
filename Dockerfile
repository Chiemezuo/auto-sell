# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ── Stage 2: production image ─────────────────────────────────────────────────
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=auto_sell.settings.production

# Create a non-root user that will own and run the app
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --home /home/appuser --shell /bin/sh appuser \
    && mkdir -p /home/appuser \
    && chown appuser:appgroup /home/appuser

WORKDIR /app

# Copy installed packages from builder (no pip in final image)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code
COPY --chown=appuser:appgroup . .

# Collect static files at build time — dummy SECRET_KEY since no .env exists in CI/Coolify
RUN SECRET_KEY=build-only-placeholder python manage.py collectstatic --noinput

RUN chmod +x entrypoint.sh

# Switch to non-root user for runtime
USER appuser

EXPOSE 8000

CMD ["./entrypoint.sh"]
