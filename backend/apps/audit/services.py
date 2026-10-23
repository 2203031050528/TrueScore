import json

from django.core.serializers.json import DjangoJSONEncoder

from apps.core.utils import client_ip

from .models import AuditLog

# Never persist these, even if a caller passes a whole object snapshot.
REDACTED_KEYS = {"password", "password_hash", "token", "access", "refresh", "access_code", "seb_config_key"}


def _clean(value):
    if value is None:
        return None
    value = json.loads(json.dumps(value, cls=DjangoJSONEncoder))
    if isinstance(value, dict):
        return {k: ("[redacted]" if k in REDACTED_KEYS else v) for k, v in value.items()}
    return value


def audit(request, action, entity, entity_id="", before=None, after=None, reason=""):
    actor = getattr(request, "user", None) if request is not None else None
    return AuditLog.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id or ""),
        before=_clean(before),
        after=_clean(after),
        reason=reason or "",
        ip=client_ip(request) if request is not None else None,
    )
