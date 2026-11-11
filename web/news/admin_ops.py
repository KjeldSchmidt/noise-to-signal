"""Staff-only admin UI for story-thread maintenance / requeue ops."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from news.services.requeue import articles_for_requeue, requeue_articles
from news.services.threading import dissolve_singleton_threads, reconcile_story_threads


class RequeueForm(forms.Form):
    all_articles = forms.BooleanField(
        required=False,
        label="All articles",
    )
    unthreaded = forms.BooleanField(
        required=False,
        label="Unthreaded only",
    )
    ids = forms.CharField(
        required=False,
        label="Article IDs",
        help_text="Comma-separated primary keys",
        widget=forms.TextInput(attrs={"size": 40}),
    )
    since = forms.CharField(
        required=False,
        label="Published since",
        help_text="ISO datetime, e.g. 2026-11-01T00:00:00+00:00",
        widget=forms.TextInput(attrs={"size": 40}),
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


@require_http_methods(["GET", "POST"])
def news_ops_view(request):
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
                stats = reconcile_story_threads(
                    limit=reconcile_form.cleaned_data.get("limit")
                )
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
                        ids = [
                            int(x.strip()) for x in ids_raw.split(",") if x.strip()
                        ]
                    except ValueError:
                        messages.error(
                            request, "Article IDs must be comma-separated integers."
                        )
                        return redirect("admin:news_ops")
                since = None
                since_raw = (data.get("since") or "").strip()
                if since_raw:
                    since = parse_datetime(since_raw)
                    if since is None:
                        messages.error(request, "Published since must be an ISO datetime.")
                        return redirect("admin:news_ops")
                try:
                    qs = articles_for_requeue(
                        all_articles=bool(data.get("all_articles")),
                        unthreaded=bool(data.get("unthreaded")),
                        ids=ids,
                        since=since,
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


def patch_admin_urls() -> None:
    """Register /admin/news/ops/ on the default AdminSite."""
    if getattr(admin.site, "_news_ops_urls_patched", False):
        return

    original_get_urls = admin.site.get_urls

    def get_urls():
        return [
            path(
                "news/ops/",
                admin.site.admin_view(news_ops_view),
                name="news_ops",
            ),
            *original_get_urls(),
        ]

    admin.site.get_urls = get_urls  # type: ignore[method-assign]
    admin.site._news_ops_urls_patched = True  # type: ignore[attr-defined]


def ops_admin_url() -> str:
    return reverse("admin:news_ops")
