from django.conf import settings
from django.db import models


class Video(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    chapter = models.ForeignKey("academics.Chapter", on_delete=models.PROTECT, related_name="videos")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    r2_key = models.CharField(max_length=255)
    duration_s = models.PositiveIntegerField()
    thumbnail_key = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    order = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "videos"
        ordering = ["chapter__order", "order", "id"]
        indexes = [models.Index(fields=["chapter", "status", "order"])]

    def __str__(self):
        return self.title


class WatchProgress(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watch_progress")
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="progress")
    last_position_s = models.PositiveIntegerField(default=0)
    seconds_watched = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "watch_progress"
        constraints = [models.UniqueConstraint(fields=["student", "video"], name="unique_watch_progress")]
        indexes = [models.Index(fields=["student"])]
