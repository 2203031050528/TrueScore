import ipaddress
import secrets
import string

from django.conf import settings

TOKEN_ALPHABET = string.ascii_letters + string.digits
# No easily-confused characters in passwords we hand to children.
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def client_ip(request):
    """Client IP honouring exactly TRUSTED_PROXY_COUNT reverse proxies.

    Each trusted proxy appends the address it received the request from, so the client is the entry
    TRUSTED_PROXY_COUNT positions from the right. Anything further left is client-controlled.
    """
    remote = request.META.get("REMOTE_ADDR", "")
    hops = settings.TRUSTED_PROXY_COUNT
    if hops <= 0:
        return remote
    forwarded = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    if len(forwarded) >= hops:
        return forwarded[-hops]
    return forwarded[0] if forwarded else remote


def ip_in_allowlist(ip, allowlist):
    if not allowlist:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def random_token(length=10):
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(length))


def random_password(length=10):
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))
