from django.http import HttpRequest, JsonResponse


def health(_request: HttpRequest) -> JsonResponse:
    """Liveness probe for deploy smoke checks."""
    return JsonResponse({"status": "ok"})
