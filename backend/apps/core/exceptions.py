from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """DRF handler that keeps a stable `{detail, code}` shape for the frontend."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict) and "detail" in data:
        detail = data["detail"]
        if not isinstance(detail, dict):
            response.data = {"detail": str(detail), "code": getattr(detail, "code", None)}
    return response
