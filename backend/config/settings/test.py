from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key-that-is-long-enough-for-hs256-signing"
SIMPLE_JWT = {**SIMPLE_JWT, "SIGNING_KEY": SECRET_KEY}  # noqa: F405
AUTH_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
INTERNAL_CRON_SECRET = "test-internal-secret"
R2_ACCOUNT_ID = ""
MEDIA_ROOT = BASE_DIR / ".test-media"  # noqa: F405
REST_FRAMEWORK = {**REST_FRAMEWORK}  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {k: "10000/min" for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]}
