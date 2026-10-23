import sentry_sdk

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

if SECRET_KEY == "dev-insecure-change-me":  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production")
if not INTERNAL_CRON_SECRET:  # noqa: F405
    raise RuntimeError("INTERNAL_CRON_SECRET must be set in production")

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
AUTH_COOKIE_SECURE = True
SECURE_REDIRECT_EXEMPT = [r"^api/v1/internal/warmup$"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

if env("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=env("SENTRY_DSN"),
        send_default_pii=False,
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        environment=env("SENTRY_ENVIRONMENT", "production"),
    )
