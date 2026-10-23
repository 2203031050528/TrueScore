from django.contrib import admin

from .models import Exam, ExamPart, ExamQuestion, ExamTarget, Question, QuestionOption


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["id", "subject", "chapter", "type", "difficulty", "marks", "version", "is_active"]
    list_filter = ["type", "difficulty", "is_active", "subject__school_class"]
    search_fields = ["text"]
    inlines = [QuestionOptionInline]


class ExamTargetInline(admin.TabularInline):
    model = ExamTarget
    extra = 0


class ExamPartInline(admin.TabularInline):
    model = ExamPart
    extra = 0


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ["title", "school_class", "subject", "start_at", "end_at", "status"]
    list_filter = ["status", "school_class"]
    inlines = [ExamTargetInline, ExamPartInline]


admin.site.register(ExamQuestion)
