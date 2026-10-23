from rest_framework.throttling import SimpleRateThrottle

from .utils import client_ip


class _UserOrIpThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"u{request.user.pk}"
        else:
            ident = client_ip(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginThrottle(_UserOrIpThrottle):
    scope = "login"


class PasswordThrottle(_UserOrIpThrottle):
    scope = "password"


class AnswerThrottle(_UserOrIpThrottle):
    scope = "answers"


class EventThrottle(_UserOrIpThrottle):
    scope = "events"


class VideoUrlThrottle(_UserOrIpThrottle):
    scope = "video_url"


class AdminThrottle(_UserOrIpThrottle):
    scope = "admin"


class InternalThrottle(_UserOrIpThrottle):
    scope = "internal"
