from rest_framework import viewsets

from apps.audit.services import audit
from apps.core.permissions import IsAdmin
from apps.core.throttles import AdminThrottle


class AuditedAdminViewSet(viewsets.ModelViewSet):
    """Admin-only CRUD where every create/update/delete is written to the audit log."""

    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]
    audit_entity = ""

    def _entity(self):
        return self.audit_entity or self.get_queryset().model._meta.db_table

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, f"{self._entity()}.create", self._entity(), obj.pk, after=serializer.data)

    def perform_update(self, serializer):
        before = self.get_serializer(serializer.instance).data
        obj = serializer.save()
        audit(self.request, f"{self._entity()}.update", self._entity(), obj.pk, before=before, after=serializer.data)

    def perform_destroy(self, instance):
        before = self.get_serializer(instance).data
        pk = instance.pk
        instance.delete()
        audit(self.request, f"{self._entity()}.delete", self._entity(), pk, before=before)
