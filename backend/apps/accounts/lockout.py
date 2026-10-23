"""Login brute-force protection: N failures per username or per IP → temporary lockout."""

from django.conf import settings
from django.core.cache import cache


def _keys(username, ip):
    return [f"login-fail:u:{username.lower()}", f"login-fail:ip:{ip}"]


def is_locked(username, ip):
    limit = settings.LOGIN_MAX_FAILURES
    user_key, ip_key = _keys(username, ip)
    # The per-IP budget is larger: a school lab shares one public IP.
    return (cache.get(user_key, 0) >= limit) or (cache.get(ip_key, 0) >= limit * 10)


def register_failure(username, ip):
    for key in _keys(username, ip):
        if cache.add(key, 1, timeout=settings.LOGIN_LOCKOUT_SECONDS):
            continue
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=settings.LOGIN_LOCKOUT_SECONDS)


def clear(username):
    cache.delete(_keys(username, "")[0])
