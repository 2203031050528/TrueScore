"""Settings shared by every environment. Environment-specific files import * from here."""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "apps.core",
    "apps.audit",
    "apps.academics",
    "apps.accounts",
    "apps.videos",
    "apps.exams",
    "apps.attempts",
    "apps.results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://localhost:5432/truescore"),
        conn_max_age=60,
        conn_health_checks=True,
    )
}

REDIS_URL = env("REDIS_URL")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "ts",
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---------------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.CookieJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.core.permissions.PasswordChanged",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "password": "5/min",
        "answers": "120/min",
        "events": "60/min",
        "video_url": "30/min",
        "admin": "600/min",
        "internal": "30/min",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY", SECRET_KEY),
    "ALGORITHM": "HS256",
    "USER_ID_CLAIM": "user_id",
}

# --- Cookies & CSRF --------------------------------------------------------------------------
AUTH_COOKIE_SECURE = True
AUTH_COOKIE_SAMESITE = "Lax"
AUTH_ACCESS_COOKIE = "ts_access"
AUTH_REFRESH_COOKIE = "ts_refresh"
AUTH_REFRESH_COOKIE_PATH = "/api/v1/auth/"
DEVICE_COOKIE = "ts_device"
ROLE_COOKIE = "ts_role"

CSRF_COOKIE_HTTPONLY = False  # the SPA must read it to send X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:3000")
SESSION_COOKIE_SAMESITE = "Lax"

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOW_CREDENTIALS = True

# --- Security headers ------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- App settings ----------------------------------------------------------------------------
TRUSTED_PROXY_COUNT = int(env("TRUSTED_PROXY_COUNT", "0"))
INTERNAL_CRON_SECRET = env("INTERNAL_CRON_SECRET", "")
# Public origin of the frontend (used to verify Safe Exam Browser config-key hashes)
PUBLIC_ORIGIN = env("PUBLIC_ORIGIN", "")

LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

EXAM_GRACE_SECONDS = 10
EXAM_DISCONNECT_SECONDS = 60

VIDEO_URL_TTL = int(env("VIDEO_URL_TTL", "300"))
VIDEO_UPLOAD_URL_TTL = int(env("VIDEO_UPLOAD_URL_TTL", "3600"))
VIDEO_COMPLETE_RATIO = 0.9
VIDEO_HEARTBEAT_MAX_DELTA = 20
VIDEO_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
IMAGE_MAX_UPLOAD_BYTES = 2 * 1024 * 1024

R2_ACCOUNT_ID = env("R2_ACCOUNT_ID", "")
R2_BUCKET = env("R2_BUCKET", "")
R2_READ_ACCESS_KEY_ID = env("R2_READ_ACCESS_KEY_ID", "")
R2_READ_SECRET_ACCESS_KEY = env("R2_READ_SECRET_ACCESS_KEY", "")
R2_WRITE_ACCESS_KEY_ID = env("R2_WRITE_ACCESS_KEY_ID", "")
R2_WRITE_SECRET_ACCESS_KEY = env("R2_WRITE_SECRET_ACCESS_KEY", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"level": "WARNING"}},
}
