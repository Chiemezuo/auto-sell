from .base import *  # noqa: F401, F403
import environ

env = environ.Env()

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# Needed behind a reverse proxy (Coolify/Traefik) — Django 4+ checks POST requests'
# Origin/Referer against this list, and same-origin alone isn't enough once SSL
# termination happens upstream. e.g. CSRF_TRUSTED_ORIGINS=https://autosell.yourdomain.com
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# SSL settings — disable these when running without HTTPS (e.g. IP-only deployments).
# Set HTTPS=true in env once a domain + SSL cert is in place.
_https = env.bool("HTTPS", default=False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if _https else None
SECURE_SSL_REDIRECT = _https
SESSION_COOKIE_SECURE = _https
CSRF_COOKIE_SECURE = _https
