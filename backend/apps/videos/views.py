from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdmin, IsStudent
from apps.core.storage import StorageError, get_storage, new_key
from apps.core.throttles import AdminThrottle, VideoUrlThrottle
from apps.core.viewsets import AuditedAdminViewSet

from .models import Video, WatchProgress
from .serializers import AdminVideoSerializer, HeartbeatSerializer, StudentVideoSerializer, UploadUrlSerializer

MAX_PLAYBACK_RATE = 2.0


# --- Admin ---------------------------------------------------------------------------------------


class UploadUrlView(APIView):
    """Presigned PUT URL: the browser uploads straight to storage; Django never handles the bytes."""

    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]

    def post(self, request):
        s = UploadUrlSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        kind, content_type, size = s.validated_data["kind"], s.validated_data["content_type"], s.validated_data["size"]
        limit = settings.VIDEO_MAX_UPLOAD_BYTES if kind == "videos" else settings.IMAGE_MAX_UPLOAD_BYTES
        if size > limit:
            return Response({"detail": f"File is larger than the {limit // (1024 * 1024)} MB limit."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            key = new_key(kind, content_type)
        except StorageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        upload = get_storage().upload_url(key, content_type, settings.VIDEO_UPLOAD_URL_TTL)
        return Response({"key": key, "upload": upload, "expires_in": settings.VIDEO_UPLOAD_URL_TTL})


class AdminVideoViewSet(AuditedAdminViewSet):
    serializer_class = AdminVideoSerializer
    audit_entity = "videos"

    def get_queryset(self):
        qs = Video.objects.select_related("chapter__subject__school_class")
        p = self.request.query_params
        if p.get("class_id"):
            qs = qs.filter(chapter__subject__school_class_id=p["class_id"])
        if p.get("subject_id"):
            qs = qs.filter(chapter__subject_id=p["subject_id"])
        if p.get("chapter_id"):
            qs = qs.filter(chapter_id=p["chapter_id"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        return qs.order_by("chapter__subject__school_class__grade", "chapter__subject__name", "chapter__order", "order", "id")

    def perform_create(self, serializer):
        obj = serializer.save(uploaded_by=self.request.user)
        from apps.audit.services import audit

        audit(self.request, "videos.create", "videos", obj.pk, after=serializer.data)

    @action(detail=True, methods=["get"], url_path="play-url")
    def play_url(self, request, pk=None):
        video = self.get_object()
        return Response(_play_payload(video))


# --- Student -------------------------------------------------------------------------------------


def _play_payload(video):
    storage = get_storage()
    ttl = settings.VIDEO_URL_TTL
    return {
        "url": storage.download_url(video.r2_key, ttl),
        "thumbnail_url": storage.download_url(video.thumbnail_key, ttl) if video.thumbnail_key else None,
        "expires_in": ttl,
    }


def student_videos(user):
    """Published videos of the student's own class only, with that student's progress prefetched."""
    return (
        Video.objects.filter(status=Video.Status.PUBLISHED, chapter__subject__school_class_id=user.student_profile.school_class_id)
        .select_related("chapter__subject")
        .prefetch_related(Prefetch("progress", queryset=WatchProgress.objects.filter(student=user), to_attr="my_progress"))
        .order_by("chapter__subject__name", "chapter__order", "order", "id")
    )


class StudentVideoListView(generics.ListAPIView):
    permission_classes = [IsStudent]
    serializer_class = StudentVideoSerializer
    pagination_class = None

    def get_queryset(self):
        qs = student_videos(self.request.user)
        p = self.request.query_params
        if p.get("subject"):
            qs = qs.filter(chapter__subject_id=p["subject"])
        if p.get("chapter"):
            qs = qs.filter(chapter_id=p["chapter"])
        if p.get("in_progress") == "true":
            qs = qs.filter(progress__student=self.request.user, progress__completed_at__isnull=True, progress__last_position_s__gt=0)
        return qs


class StudentVideoDetailView(generics.RetrieveAPIView):
    permission_classes = [IsStudent]
    serializer_class = StudentVideoSerializer

    def get_queryset(self):
        return student_videos(self.request.user)


class PlayUrlView(APIView):
    permission_classes = [IsStudent]
    throttle_classes = [VideoUrlThrottle]

    def get(self, request, pk):
        video = get_object_or_404(student_videos(request.user), pk=pk)
        return Response(_play_payload(video))


class ProgressHeartbeatView(APIView):
    """15-second watch heartbeat. Credited time is capped so progress cannot be faked by a script."""

    permission_classes = [IsStudent]
    throttle_classes = [VideoUrlThrottle]
    throttle_scope = "video_url"

    def post(self, request, pk):
        video = get_object_or_404(student_videos(request.user), pk=pk)
        s = HeartbeatSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        now = timezone.now()
        with transaction.atomic():
            progress, created = WatchProgress.objects.select_for_update().get_or_create(student=request.user, video=video)
            if created:
                elapsed = settings.VIDEO_HEARTBEAT_MAX_DELTA
            else:
                elapsed = max(0.0, (now - progress.updated_at).total_seconds())
            credited = int(min(s.validated_data["delta_s"], settings.VIDEO_HEARTBEAT_MAX_DELTA, elapsed * MAX_PLAYBACK_RATE + 1))
            progress.seconds_watched = min(video.duration_s, progress.seconds_watched + credited)
            progress.last_position_s = min(video.duration_s, s.validated_data["position_s"])
            if progress.completed_at is None and progress.seconds_watched >= settings.VIDEO_COMPLETE_RATIO * video.duration_s:
                progress.completed_at = now
            progress.save()
        return Response(
            {
                "last_position_s": progress.last_position_s,
                "seconds_watched": progress.seconds_watched,
                "completed": progress.completed_at is not None,
            }
        )
