from .base import *  # noqa: F401,F403

DEBUG = True
AUTH_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
INTERNAL_CRON_SECRET = INTERNAL_CRON_SECRET or "dev-internal-secret"  # noqa: F405
