from django.contrib import admin

from .models import ResultPublication


@admin.register(ResultPublication)
class ResultPublicationAdmin(admin.ModelAdmin):
    list_display = ["exam", "section", "published_by", "published_at", "show_answers"]
