from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


def enforce_csrf(request):
    def dummy_get_response(_request):  # pragma: no cover - never called
        return None

    check = CSRFCheck(dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")


class CookieJWTAuthentication(JWTAuthentication):
    """JWT read from the httpOnly access cookie, bound to the user's token_version, CSRF-protected.

    The Authorization header is deliberately not accepted: tokens never live in JS-readable storage.
    """

    def authenticate(self, request):
        raw = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE)
        if not raw:
            return None
        try:
            token = self.get_validated_token(raw)
        except (InvalidToken, TokenError):
            raise exceptions.AuthenticationFailed("Session expired.", code="token_expired") from None
        user = self.get_user(token)
        if not user.is_active:
            raise exceptions.AuthenticationFailed("Account suspended.", code="user_inactive")
        if token.get("tv") != user.token_version:
            raise exceptions.AuthenticationFailed("Session revoked.", code="token_revoked")
        enforce_csrf(request._request)
        return user, token

    def authenticate_header(self, request):
        # Makes DRF answer 401 (not 403) for missing/expired credentials so the client knows to refresh.
        return 'Cookie realm="api"'
