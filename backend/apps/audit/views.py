from rest_framework import generics

from apps.core.permissions import IsAdmin
from apps.core.throttles import AdminThrottle

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    throttle_classes = [AdminThrottle]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor")
        params = self.request.query_params
        if params.get("entity"):
            qs = qs.filter(entity=params["entity"])
        if params.get("entity_id"):
            qs = qs.filter(entity_id=params["entity_id"])
        if params.get("action"):
            qs = qs.filter(action=params["action"])
        if params.get("actor"):
            qs = qs.filter(actor__username=params["actor"])
        return qs
