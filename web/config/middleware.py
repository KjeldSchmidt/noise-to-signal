"""Request tweaks for CloudFront → Lambda Function URL."""

from __future__ import annotations

import os

from django.http import HttpRequest
from django.urls import Resolver404, resolve


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
