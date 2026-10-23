API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class SecurityHeadersMiddleware:
    """Strict headers for API responses; the Next.js app sets its own CSP for pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        if request.path.startswith("/api/"):
            response.setdefault("Content-Security-Policy", API_CSP)
            response["Cache-Control"] = "no-store"
            response["Pragma"] = "no-cache"
        return response
