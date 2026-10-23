from rest_framework import serializers

from apps.academics.models import Chapter
from apps.core.storage import StorageError, get_storage, validate_key

from .models import Video, WatchProgress


class UploadUrlSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["videos", "thumbnails", "questions", "photos"])
    content_type = serializers.CharField(max_length=64)
    size = serializers.IntegerField(min_value=1)


class AdminVideoSerializer(serializers.ModelSerializer):
    chapter = serializers.PrimaryKeyRelatedField(queryset=Chapter.objects.select_related("subject__school_class"))
    chapter_name = serializers.CharField(source="chapter.name", read_only=True)
    subject_id = serializers.IntegerField(source="chapter.subject_id", read_only=True)
    subject_name = serializers.CharField(source="chapter.subject.name", read_only=True)
    grade = serializers.IntegerField(source="chapter.subject.school_class.grade", read_only=True)

    class Meta:
        model = Video
        fields = [
            "id",
            "chapter",
            "chapter_name",
            "subject_id",
            "subject_name",
            "grade",
            "title",
            "description",
            "r2_key",
            "duration_s",
            "thumbnail_key",
            "status",
            "order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def _validate_stored(self, value, prefix):
        try:
            validate_key(value)
        except StorageError as exc:
            raise serializers.ValidationError(str(exc)) from None
        if not value.startswith(prefix):
            raise serializers.ValidationError(f"Key must start with {prefix}")
        if not get_storage().exists(value):
            raise serializers.ValidationError("No uploaded file found for this key. Upload it first.")
        return value

    def validate_r2_key(self, value):
        if self.instance and self.instance.r2_key == value:
            return value
        return self._validate_stored(value, "videos/")

    def validate_thumbnail_key(self, value):
        if not value or (self.instance and self.instance.thumbnail_key == value):
            return value
        return self._validate_stored(value, "thumbnails/")

    def validate_duration_s(self, value):
        if value < 1 or value > 6 * 3600:
            raise serializers.ValidationError("Duration must be between 1 second and 6 hours.")
        return value


class StudentVideoSerializer(serializers.ModelSerializer):
    chapter_name = serializers.CharField(source="chapter.name", read_only=True)
    subject_id = serializers.IntegerField(source="chapter.subject_id", read_only=True)
    subject_name = serializers.CharField(source="chapter.subject.name", read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = ["id", "chapter", "chapter_name", "subject_id", "subject_name", "title", "description", "duration_s", "order", "progress"]

    def get_progress(self, video):
        # `my_progress` is prefetched with only the current student's row.
        rows = getattr(video, "my_progress", None)
        p = rows[0] if rows else None
        if p is None:
            return {"last_position_s": 0, "seconds_watched": 0, "percent": 0, "completed": False}
        return {
            "last_position_s": p.last_position_s,
            "seconds_watched": p.seconds_watched,
            "percent": min(100, round(100 * p.seconds_watched / video.duration_s)) if video.duration_s else 0,
            "completed": p.completed_at is not None,
        }


class HeartbeatSerializer(serializers.Serializer):
    position_s = serializers.IntegerField(min_value=0)
    delta_s = serializers.IntegerField(min_value=0, max_value=3600)


class WatchProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchProgress
        fields = ["last_position_s", "seconds_watched", "completed_at"]
