from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.academics import views as academics
from apps.accounts import views as accounts
from apps.attempts import views as attempts
from apps.audit.views import AuditLogListView
from apps.core import views as core
from apps.exams import views as exams
from apps.results import views as results
from apps.videos import views as videos

admin_router = DefaultRouter(trailing_slash=False)
admin_router.register("students", accounts.StudentViewSet, basename="admin-students")
admin_router.register("academic-years", academics.AcademicYearViewSet, basename="admin-years")
admin_router.register("classes", academics.SchoolClassViewSet, basename="admin-classes")
admin_router.register("sections", academics.SectionViewSet, basename="admin-sections")
admin_router.register("subjects", academics.SubjectViewSet, basename="admin-subjects")
admin_router.register("chapters", academics.ChapterViewSet, basename="admin-chapters")
admin_router.register("videos", videos.AdminVideoViewSet, basename="admin-videos")
admin_router.register("questions", exams.QuestionViewSet, basename="admin-questions")
admin_router.register("exams", exams.ExamViewSet, basename="admin-exams")
admin_router.register("exam-parts", exams.ExamPartViewSet, basename="admin-exam-parts")
admin_router.register("exam-questions", exams.ExamQuestionViewSet, basename="admin-exam-questions")

admin_api = [
    path("videos/upload-url", videos.UploadUrlView.as_view(), name="admin-upload-url"),
    path("promote", accounts.PromoteView.as_view(), name="admin-promote"),
    path("audit", AuditLogListView.as_view(), name="admin-audit"),
    path("exams/<int:exam_id>/monitor", attempts.ExamMonitorView.as_view(), name="admin-exam-monitor"),
    path("exams/<int:exam_id>/analytics", results.AnalyticsView.as_view(), name="admin-exam-analytics"),
    path("exams/<int:exam_id>/attempts", results.ExamAttemptsView.as_view(), name="admin-exam-attempts"),
    path("exams/<int:exam_id>/marking", attempts.MarkingQueueView.as_view(), name="admin-exam-marking"),
    path("exams/<int:exam_id>/regrade", results.RegradeView.as_view(), name="admin-exam-regrade"),
    path("exams/<int:exam_id>/publish", results.PublishView.as_view(), name="admin-exam-publish"),
    path("exams/<int:exam_id>/unpublish", results.UnpublishView.as_view(), name="admin-exam-unpublish"),
    path("attempts/<int:attempt_id>", attempts.AttemptReviewView.as_view(), name="admin-attempt-review"),
    path(
        "attempts/<int:attempt_id>/<str:op>",
        attempts.AttemptInterventionView.as_view(),
        name="admin-attempt-intervene",
    ),
    path("answers/<int:answer_id>/mark", attempts.MarkAnswerView.as_view(), name="admin-answer-mark"),
    path("", include(admin_router.urls)),
]

api_v1 = [
    # Auth
    path("auth/csrf", accounts.CsrfView.as_view(), name="auth-csrf"),
    path("auth/login", accounts.LoginView.as_view(), name="auth-login"),
    path("auth/refresh", accounts.RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", accounts.LogoutView.as_view(), name="auth-logout"),
    path("auth/change-password", accounts.ChangePasswordView.as_view(), name="auth-change-password"),
    path("me", accounts.MeView.as_view(), name="me"),
    path("me/progress", results.ProgressView.as_view(), name="me-progress"),
    # Student
    path("subjects", academics.StudentSubjectsView.as_view(), name="student-subjects"),
    path("videos", videos.StudentVideoListView.as_view(), name="student-videos"),
    path("videos/<int:pk>", videos.StudentVideoDetailView.as_view(), name="student-video"),
    path("videos/<int:pk>/play-url", videos.PlayUrlView.as_view(), name="student-video-play"),
    path("videos/<int:pk>/progress", videos.ProgressHeartbeatView.as_view(), name="student-video-progress"),
    path("exams/upcoming", attempts.UpcomingExamsView.as_view(), name="student-exams"),
    path("exams/<int:exam_id>/start", attempts.StartAttemptView.as_view(), name="student-exam-start"),
    path("attempts/<int:attempt_id>", attempts.AttemptDetailView.as_view(), name="student-attempt"),
    path("attempts/<int:attempt_id>/answers/<int:question_id>", attempts.SaveAnswerView.as_view(), name="student-answer"),
    path("attempts/<int:attempt_id>/events", attempts.AttemptEventsView.as_view(), name="student-events"),
    path("attempts/<int:attempt_id>/submit", attempts.SubmitAttemptView.as_view(), name="student-submit"),
    path("results", results.StudentResultListView.as_view(), name="student-results"),
    path("results/<int:exam_id>", results.StudentResultDetailView.as_view(), name="student-result"),
    # Admin and internal live under separate prefixes so they are throttled and logged separately.
    path("admin/", include(admin_api)),
    path("internal/sweep-attempts", attempts.SweepAttemptsView.as_view(), name="internal-sweep"),
    path("internal/warmup", attempts.WarmupView.as_view(), name="internal-warmup"),
    # Local signed storage (only active when R2 is not configured).
    path("dev-storage/upload/<str:token>", core.dev_upload, name="dev-storage-upload"),
    path("dev-storage/file/<str:token>", core.dev_download, name="dev-storage-download"),
]

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
]
