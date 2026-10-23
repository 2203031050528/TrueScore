from django.contrib import admin

from .models import Video, WatchProgress


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ["title", "chapter", "status", "order", "duration_s"]
    list_filter = ["status", "chapter__subject__school_class"]
    search_fields = ["title"]


@admin.register(WatchProgress)
class WatchProgressAdmin(admin.ModelAdmin):
    list_display = ["student", "video", "seconds_watched", "completed_at"]
