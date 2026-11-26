from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def health(_request: HttpRequest) -> JsonResponse:
    """Liveness probe for deploy smoke checks."""
    return JsonResponse({"status": "ok"})


def page_not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Public 404 with the standard site chrome."""
    _ = exception
    return render(request, "404.html", status=404)
