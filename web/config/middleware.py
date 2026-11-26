"""Request tweaks for CloudFront → Lambda Function URL."""

from __future__ import annotations

import os

from django.http import HttpRequest, HttpResponse
from django.urls import Resolver404, resolve
from django.utils import translation

_PRODUCT_UI_LOCALES = frozenset({"en", "fr", "de"})


class ActivatePrimaryLanguageMiddleware:
    """Override active locale from the user's primary content language."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        code = "en"
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            from news.services.feeds import primary_content_language

            code = primary_content_language(user)
        if code not in _PRODUCT_UI_LOCALES:
            code = "en"
        translation.activate(code)
        request.LANGUAGE_CODE = code
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", code)
        translation.deactivate()
        return response


class ViewerHostMiddleware:
    """Promote CloudFront ``X-Viewer-Host`` so absolute URLs / CSRF use the public host.

    CloudFront Functions cannot set ``X-Forwarded-Host`` (disallowed → 502), so the
    distribution copies the viewer Host into ``X-Viewer-Host`` instead. Origin Host
    remains the Lambda Function URL hostname.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.on_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    def __call__(self, request: HttpRequest):
        viewer_host = request.headers.get("X-Viewer-Host", "").strip()
        if viewer_host:
            request.META["HTTP_X_FORWARDED_HOST"] = viewer_host
        if viewer_host or self.on_lambda:
            request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        return self.get_response(request)


class NormalizeTrailingSlashMiddleware:
    """Resolve URLs that need a trailing slash without issuing a redirect.

    Avoids the APPEND_SLASH ↔ proxy slash-strip loop (301 Location to the same path).

    Prefer the trailing-slash route whenever it resolves. Otherwise Django admin's
    catch-all can match ``/admin/login`` (no slash), ``admin_view`` calls
    ``redirect_to_login``, and CloudFront slash-stripping nests ``?next=`` forever.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        path = request.path_info
        if path != "/" and not path.endswith("/"):
            slashed = f"{path}/"
            try:
                resolve(slashed)
            except Resolver404:
                pass
            else:
                request.path_info = slashed
                # Keep path in sync for get_full_path() / redirects.
                if not request.path.endswith("/"):
                    request.path = f"{request.path}/"
        return self.get_response(request)
