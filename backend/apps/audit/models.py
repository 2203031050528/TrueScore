from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only record of every admin action. Rows can be created, never changed or deleted."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=64)
    entity = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["entity", "entity_id"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Audit log entries are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log entries are append-only.")

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} {self.entity}#{self.entity_id}"
