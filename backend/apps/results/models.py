from django.conf import settings
from django.db import models


class ResultPublication(models.Model):
    """Results of an exam are visible to a section only once a row exists here (enforced at the API)."""

    exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE, related_name="publications")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="+")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    published_at = models.DateTimeField(auto_now_add=True)
    show_answers = models.BooleanField(default=True)

    class Meta:
        db_table = "result_publications"
        constraints = [models.UniqueConstraint(fields=["exam", "section"], name="unique_publication_per_section")]
