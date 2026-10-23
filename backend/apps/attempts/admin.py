from django.contrib import admin

from .models import Attempt, ProctorEvent


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ["id", "exam", "student", "section", "status", "score", "rank", "flag_count"]
    list_filter = ["status", "grading_status"]
    readonly_fields = ["question_order"]


@admin.register(ProctorEvent)
class ProctorEventAdmin(admin.ModelAdmin):
    list_display = ["attempt", "type", "occurred_at"]
    list_filter = ["type"]
