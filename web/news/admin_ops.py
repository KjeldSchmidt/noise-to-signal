"""Staff-only admin UI for story-thread maintenance / requeue ops."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.views.decorators.http import require_http_methods

from news.admin_custom_pages import custom_admin_page, iter_custom_admin_pages
from news.services.requeue import articles_for_requeue, requeue_articles
from news.services.threading import dissolve_singleton_threads, reconcile_story_threads

_ADMIN_SITE_PATCHED = False


class RequeueForm(forms.Form):
    all_articles = forms.BooleanField(
        required=False,
        label="All articles",
    )
    unthreaded = forms.BooleanField(
        required=False,
        label="Unthreaded only",
    )
    degraded_only = forms.BooleanField(
        required=False,
        label="Degraded enrichment status only",
        help_text="Articles where geocode soft-failed (enrichment_status=degraded).",
    )
    ids = forms.CharField(
        required=False,
        label="Article IDs",
        help_text="Comma-separated primary keys",
        widget=forms.TextInput(attrs={"size": 40}),
    )
    since_hours = forms.IntegerField(
        required=False,
        min_value=1,
        label="Published within last N hours",
        help_text="e.g. 24 for the last day, 168 for the last week",
    )
    enriched_before_hours = forms.IntegerField(
        required=False,
        min_value=1,
        label="Enriched before last N hours",
        help_text=(
            "Skip articles enriched within the last N hours (never-enriched still "
            "included). Use after a test pass, e.g. publish window 72 + enriched "
            "before 1 to widen without redoing the last hour."
        ),
    )
    clear_threads = forms.BooleanField(
        required=False,
        label="Clear story threads before enqueue",
        help_text="Needed if you want assign_story_thread to run again after enrich.",
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label="Dry run (count only)",
    )


class ReconcileForm(forms.Form):
    limit = forms.IntegerField(
        required=False,
        min_value=1,
        label="Limit",
        help_text="Optional max unthreaded articles (oldest first).",
    )


@custom_admin_page(
    name="news_ops",
    path="news/ops/",
    title="News ops",
    description="Dissolve / reconcile story threads and requeue article enrichment.",
)
@require_http_methods(["GET", "POST"])
def news_ops_view(request: HttpRequest) -> HttpResponse:
    """Custom admin page: dissolve / reconcile / requeue."""
    requeue_form = RequeueForm(prefix="requeue")
    reconcile_form = ReconcileForm(prefix="reconcile")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "dissolve":
            cleared, deleted = dissolve_singleton_threads()
            messages.success(
                request,
                f"Dissolve: cleared {cleared} article(s), deleted {deleted} thread(s).",
            )
            return redirect("admin:news_ops")

        if action == "reconcile":
            reconcile_form = ReconcileForm(request.POST, prefix="reconcile")
            if reconcile_form.is_valid():
                stats = reconcile_story_threads(limit=reconcile_form.cleaned_data.get("limit"))
                messages.success(
                    request,
                    "Reconcile: "
                    f"singletons_cleared={stats['singletons_cleared']}, "
                    f"threads_deleted={stats['threads_deleted']}, "
                    f"unthreaded_considered={stats['unthreaded_considered']}, "
                    f"newly_threaded={stats['newly_threaded']}.",
                )
                return redirect("admin:news_ops")

        if action == "requeue":
            requeue_form = RequeueForm(request.POST, prefix="requeue")
            if requeue_form.is_valid():
                data = requeue_form.cleaned_data
                ids_raw = (data.get("ids") or "").strip()
                ids: list[int] | None = None
                if ids_raw:
                    try:
                        ids = [int(x.strip()) for x in ids_raw.split(",") if x.strip()]
                    except ValueError:
                        messages.error(request, "Article IDs must be comma-separated integers.")
                        return redirect("admin:news_ops")
                try:
                    qs = articles_for_requeue(
                        all_articles=bool(data.get("all_articles")),
                        unthreaded=bool(data.get("unthreaded")),
                        degraded_only=bool(data.get("degraded_only")),
                        ids=ids,
                        since_hours=data.get("since_hours"),
                        enriched_before_hours=data.get("enriched_before_hours"),
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect("admin:news_ops")

                result = requeue_articles(
                    qs,
                    clear_threads=bool(data.get("clear_threads")),
                    dry_run=bool(data.get("dry_run")),
                )
                if data.get("dry_run"):
                    messages.info(
                        request,
                        f"Dry run: would requeue {result['count']} article(s).",
                    )
                else:
                    messages.success(
                        request,
                        f"Requeue: cleared={result['cleared']}, "
                        f"enqueued={result['enqueued']} / {result['count']}.",
                    )
                return redirect("admin:news_ops")

    context = {
        **admin.site.each_context(request),
        "title": "News ops",
        "requeue_form": requeue_form,
        "reconcile_form": reconcile_form,
    }
    return render(request, "admin/news/ops.html", context)


def patch_admin_site() -> None:
    """Mount annotated custom pages and expose them on the admin index."""
    global _ADMIN_SITE_PATCHED

    # Side-effect: register @custom_admin_page views defined in sibling modules.
    import news.admin_theme_analysis as _admin_theme_analysis  # noqa: F401

    if _ADMIN_SITE_PATCHED:
        return

    original_get_urls = admin.site.get_urls
    original_each_context = admin.site.each_context

    def get_urls() -> list:
        custom = [
            path(
                page.path,
                admin.site.admin_view(page.view),
                name=page.name,
            )
            for page in iter_custom_admin_pages()
        ]
        return [*custom, *original_get_urls()]

    def each_context(request: HttpRequest) -> dict[str, object]:
        ctx: dict[str, object] = dict(original_each_context(request))
        ctx["custom_admin_pages"] = [
            {
                "name": page.name,
                "title": page.title,
                "description": page.description,
                "url": reverse(f"admin:{page.name}"),
            }
            for page in iter_custom_admin_pages()
        ]
        return ctx

    admin.site.get_urls = get_urls  # type: ignore[method-assign]
    admin.site.each_context = each_context  # type: ignore[method-assign]
    _ADMIN_SITE_PATCHED = True


def patch_admin_urls() -> None:
    """Backward-compatible alias for ``patch_admin_site``."""
    patch_admin_site()


def ops_admin_url() -> str:
    return reverse("admin:news_ops")


def theme_analysis_admin_url() -> str:
    return reverse("admin:news_theme_analysis")
