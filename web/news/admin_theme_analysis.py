"""Staff-only admin UI for theme–embedding analysis artifacts."""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from news.admin_custom_pages import custom_admin_page
from news.services.theme_analysis_artifacts import load_latest, load_status, mark_running
from news.services.theme_analysis_invoke import invoke_theme_analysis


@custom_admin_page(
    name="news_theme_analysis",
    path="news/theme-analysis/",
    title="Theme analysis",
    description="Theme–embedding analysis report and async refresh.",
)
@require_http_methods(["GET", "POST"])
def theme_analysis_view(request: HttpRequest) -> HttpResponse:
    """Custom admin page: view S3 report + async Refresh."""
    configured = bool(
        (getattr(settings, "THEME_ANALYSIS_FUNCTION_NAME", None) or "").strip()
        and (getattr(settings, "ANALYSIS_ARTIFACTS_BUCKET", None) or "").strip()
    )

    if request.method == "POST":
        if not configured:
            messages.error(
                request,
                "Theme analysis is not configured "
                "(THEME_ANALYSIS_FUNCTION_NAME / ANALYSIS_ARTIFACTS_BUCKET).",
            )
            return redirect("admin:news_theme_analysis")
        try:
            mark_running()
        except Exception as exc:
            messages.error(request, f"Could not write running status: {exc}")
            return redirect("admin:news_theme_analysis")
        if invoke_theme_analysis():
            messages.success(request, "Analysis started. Refresh this page in a minute.")
        else:
            messages.error(request, "Could not invoke theme_analysis Lambda.")
        return redirect("admin:news_theme_analysis")

    status = load_status() if configured else None
    latest = load_latest() if configured else None
    context = {
        **admin.site.each_context(request),
        "title": "Theme analysis",
        "configured": configured,
        "status": status,
        "latest": latest,
    }
    return render(request, "admin/news/theme_analysis.html", context)
