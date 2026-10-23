from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


def _check_password_changed(request, view):
    """Until the first-login password change is done, only views marked `password_change_exempt` are reachable."""
    user = request.user
    if user and user.is_authenticated and user.must_change_password and not getattr(view, "password_change_exempt", False):
        raise PermissionDenied("You must change your password first.", code="password_change_required")


class PasswordChanged(BasePermission):
    def has_permission(self, request, view):
        _check_password_changed(request, view)
        return True


class _RolePermission(BasePermission):
    role = None

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        _check_password_changed(request, view)
        return user.role == self.role


class IsAdmin(_RolePermission):
    role = "admin"


class IsTeacher(_RolePermission):
    role = "teacher"


class IsStudent(_RolePermission):
    role = "student"

    def has_permission(self, request, view):
        return super().has_permission(request, view) and hasattr(request.user, "student_profile")


class InternalSecret(BasePermission):
    """Cron-only endpoints: require the shared secret header, no user session."""

    def has_permission(self, request, view):
        expected = settings.INTERNAL_CRON_SECRET
        provided = request.headers.get("X-Internal-Secret", "")
        return bool(expected) and constant_time_compare(provided, expected)
