from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.db.models import Q
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import audit
from apps.core.permissions import IsAdmin
from apps.core.throttles import AdminThrottle, LoginThrottle, PasswordThrottle
from apps.core.utils import client_ip, random_password

from . import lockout
from .authentication import enforce_csrf
from .cookies import clear_auth_cookies, ensure_device_cookie, set_auth_cookies
from .models import User
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MeSerializer,
    PromoteSerializer,
    ReasonSerializer,
    StudentSerializer,
)
from .services import ImportError_, import_students, promote_students
from .tokens import tokens_for


def _me_payload(user):
    user = User.objects.select_related(
        "student_profile__school_class", "student_profile__section__school_class", "student_profile__academic_year"
    ).get(pk=user.pk)
    return MeSerializer(user).data


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Sets the `csrftoken` cookie the SPA echoes back as X-CSRFToken."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class CsrfProtectedAnonView(APIView):
    """Endpoints that run without a session still require the CSRF token (prevents login CSRF)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        enforce_csrf(request._request)


class LoginView(CsrfProtectedAnonView):
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        ip = client_ip(request)
        if lockout.is_locked(username, ip):
            return Response(
                {"detail": "Too many failed attempts. Try again in 15 minutes.", "code": "locked_out"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        user = authenticate(request, username=username, password=serializer.validated_data["password"])
        if user is None:
            lockout.register_failure(username, ip)
            # Same message whether the user exists, is suspended, or the password is wrong.
            return Response(
                {"detail": "Invalid roll number or password.", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        lockout.clear(username)
        update_last_login(None, user)
        refresh, access = tokens_for(user)
        response = Response(_me_payload(user))
        set_auth_cookies(response, refresh, access, user)
        ensure_device_cookie(request, response)
        return response


class RefreshView(CsrfProtectedAnonView):
    """Rotates the refresh token: the old one is blacklisted, a new pair is set in cookies."""

    throttle_classes = [LoginThrottle]

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        failure = Response({"detail": "Session expired.", "code": "token_expired"}, status=status.HTTP_401_UNAUTHORIZED)
        if not raw:
            return failure
        try:
            old = RefreshToken(raw)  # verifies signature, expiry and the blacklist
            user = User.objects.get(pk=old["user_id"])
        except (TokenError, User.DoesNotExist, KeyError):
            clear_auth_cookies(failure)
            return failure
        if not user.is_active or old.get("tv") != user.token_version:
            clear_auth_cookies(failure)
            return failure
        try:
            old.blacklist()
        except TokenError:
            return failure
        refresh, access = tokens_for(user)
        response = Response({"detail": "ok"})
        set_auth_cookies(response, refresh, access, user)
        ensure_device_cookie(request, response)
        return response


class LogoutView(CsrfProtectedAnonView):
    """Works even when the access token has already expired."""

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response({"detail": "Logged out."})
        clear_auth_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    password_change_exempt = True

    def get(self, request):
        return Response(_me_payload(request.user))


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PasswordThrottle]
    password_change_exempt = True

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        user.bump_token_version()  # log out every other device
        refresh, access = tokens_for(user)
        response = Response(_me_payload(user))
        set_auth_cookies(response, refresh, access, user)
        return response


# --- Admin: students -----------------------------------------------------------------------------


class StudentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]
    serializer_class = StudentSerializer

    def get_queryset(self):
        qs = User.objects.filter(role=User.Role.STUDENT).select_related(
            "student_profile__school_class", "student_profile__section__school_class", "student_profile__academic_year"
        )
        p = self.request.query_params
        if p.get("class_id"):
            qs = qs.filter(student_profile__school_class_id=p["class_id"])
        if p.get("section_id"):
            qs = qs.filter(student_profile__section_id=p["section_id"])
        if p.get("is_active") in {"true", "false"}:
            qs = qs.filter(is_active=p["is_active"] == "true")
        if p.get("search"):
            term = p["search"].strip()
            qs = qs.filter(Q(full_name__icontains=term) | Q(username__icontains=term))
        return qs.order_by("student_profile__school_class__grade", "student_profile__section__name", "username")

    def create(self, request, *args, **kwargs):
        password = random_password()
        serializer = self.get_serializer(data=request.data, context={"request": request, "initial_password": password})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        audit(request, "student.create", "user", user.pk, after=serializer.data)
        return Response({**serializer.data, "initial_password": password}, status=status.HTTP_201_CREATED)

    def get_serializer(self, *args, **kwargs):
        kwargs.setdefault("context", self.get_serializer_context())
        return self.serializer_class(*args, **kwargs)

    def perform_update(self, serializer):
        before = StudentSerializer(serializer.instance).data
        user = serializer.save()
        audit(self.request, "student.update", "user", user.pk, before=before, after=StudentSerializer(user).data)

    def _reason(self, request):
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return s.validated_data.get("reason", "")

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = random_password()
        user.set_password(password)
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password"])
        user.bump_token_version()
        audit(request, "student.reset_password", "user", user.pk, reason=self._reason(request))
        return Response({"id": user.pk, "username": user.username, "initial_password": password})

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        user.bump_token_version()
        audit(request, "student.suspend", "user", user.pk, reason=self._reason(request))
        return Response(StudentSerializer(user).data)

    @action(detail=True, methods=["post"])
    def unsuspend(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        audit(request, "student.unsuspend", "user", user.pk, reason=self._reason(request))
        return Response(StudentSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="force-logout")
    def force_logout(self, request, pk=None):
        user = self.get_object()
        user.bump_token_version()
        audit(request, "student.force_logout", "user", user.pk, reason=self._reason(request))
        return Response({"detail": "All sessions for this student have been ended."})

    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"detail": "Upload a CSV file in the 'file' field."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            created, sections = import_students(uploaded)
        except ImportError_ as exc:
            return Response({"detail": "No students were imported.", "errors": exc.errors}, status=status.HTTP_400_BAD_REQUEST)
        audit(request, "student.import", "user", "", after={"count": len(created), "sections_created": sections})
        # Passwords are shown exactly once; they are not stored anywhere in plain text.
        return Response({"created": created, "sections_created": sections}, status=status.HTTP_201_CREATED)


class PromoteView(APIView):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def post(self, request):
        serializer = PromoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = promote_students(serializer.validated_data["new_year_label"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        audit(request, "students.promote", "academic_year", result["to_year"], after=result, reason=serializer.validated_data.get("reason", ""))
        return Response(result)
