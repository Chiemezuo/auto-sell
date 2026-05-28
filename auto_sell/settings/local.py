from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Override SECRET_KEY for local dev so .env doesn't need it
try:
    SECRET_KEY = env("SECRET_KEY")  # noqa: F405
except Exception:
    SECRET_KEY = "local-dev-secret-key-do-not-use-in-production"  # noqa: S105
