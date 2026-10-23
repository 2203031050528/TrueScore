from django.conf import settings
from rest_framework_simplejwt.settings import api_settings

from apps.core.utils import random_token


def set_auth_cookies(response, refresh, access, user):
    common = {"httponly": True, "secure": settings.AUTH_COOKIE_SECURE, "samesite": settings.AUTH_COOKIE_SAMESITE}
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE,
        str(access),
        max_age=int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
        path="/",
        **common,
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        str(refresh),
        max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        **common,
    )
    # Routing hint only, for the Next.js middleware (the refresh cookie is not visible on page routes).
    # It grants nothing: every API call is still authorised by Django from the access token.
    response.set_cookie(
        settings.ROLE_COOKIE,
        f"{user.role}:{int(user.must_change_password)}",
        max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        path="/",
        **common,
    )


def clear_auth_cookies(response):
    response.delete_cookie(settings.AUTH_ACCESS_COOKIE, path="/", samesite=settings.AUTH_COOKIE_SAMESITE)
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE, path=settings.AUTH_REFRESH_COOKIE_PATH, samesite=settings.AUTH_COOKIE_SAMESITE
    )
    response.delete_cookie(settings.ROLE_COOKIE, path="/", samesite=settings.AUTH_COOKIE_SAMESITE)


def ensure_device_cookie(request, response):
    """A random per-browser id used to enforce one device per exam attempt."""
    if request.COOKIES.get(settings.DEVICE_COOKIE):
        return
    response.set_cookie(
        settings.DEVICE_COOKIE,
        random_token(32),
        max_age=60 * 60 * 24 * 365,
        path="/",
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
