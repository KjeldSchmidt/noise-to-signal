import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AbstractBaseUser
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from n2s_api import (
    MAX_HISTORY_TURNS,
    MAX_MESSAGE_CHARS,
    BriefBuilderRequest,
    ChatHistoryMessage,
    ChatWorkerRequest,
)
from pydantic import ValidationError

from news.forms import (
    ContentLanguagesForm,
    CustomFeedForm,
    LocationOfInterestForm,
)
from news.models import (
    Article,
    Feed,
    FeedMute,
    LocationOfInterest,
    RelevanceFeedback,
    Subscription,
    UserBrief,
    UserContentLanguage,
)
from news.services import (
    DEFAULT_CONTENT_LANGUAGES,
    build_stories_feed_page,
    catalog_feed_ids,
    catalog_feeds,
    catalog_languages,
    content_language_labels,
    enabled_feed_ids,
    preferred_content_language_order,
    preferred_content_languages,
    primary_content_language,
    recommend_feeds,
    set_user_content_languages,
    thread_timeline_articles,
    thread_visible_in_scope,
)
from news.services.brief import resolve_brief_page
from news.services.brief_invoke import (
    delete_preference_memory,
    invoke_brief_builder,
    list_preference_memories,
)
from news.services.chat_invoke import invoke_news_chat
from news.services.chat_rate_limit import check_and_increment
from news.services.chat_retrieve import retrieve
from news.services.geocode import reverse_geocode_place, search_places
from news.services.theme_affinity import (
    AffinityDirection,
    AffinityLean,
    affinities_for_user,
    apply_theme_affinity_vote,
    delete_theme_affinity,
)
from news.services.thread_copy import apply_thread_display_copy


def landing(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("brief")
    # Ensure a session cookie exists before the OAuth popup opens (same-site share).
    request.session.setdefault("oauth_ready", True)
    return render(request, "news/landing.html")


def privacy(request: HttpRequest) -> HttpResponse:
    """Public privacy notice (GDPR transparency)."""
    return render(request, "news/privacy.html")


@login_required
def oauth_popup_done(request: HttpRequest) -> HttpResponse:
    """Land here after Google OAuth in a popup; close popup and navigate opener."""
    from news.views_onboarding import post_auth_next_url

    return render(
        request,
        "news/oauth_popup_done.html",
        {"next_url": post_auth_next_url(request, request.GET.get("next"))},
    )


@login_required
def brief(request: HttpRequest) -> HttpResponse:
    user = cast(AbstractBaseUser, request.user)
    state = resolve_brief_page(user)
    if state.kick and state.brief is not None:
        invoke_brief_builder(
            BriefBuilderRequest(
                action="build",
                user_id=int(user.pk),
                brief_id=state.brief.id,
            )
        )
    feed_count = len(enabled_feed_ids(user))
    preferred_order = preferred_content_language_order(user)
    for item in state.ranked:
        if item.kind == "thread" and item.thread is not None:
            apply_thread_display_copy(
                item.thread,
                preferred_order,
                fallback_title=item.article.title if item.article is not None else "",
            )
    return render(
        request,
        "news/brief.html",
        {
            "ranked": state.ranked,
            "brief_phase": state.phase,
            "brief_id": state.brief.id if state.brief else None,
            "brief_poll": state.poll,
            "feed_count": feed_count,
        },
    )


@login_required
def brief_status(request: HttpRequest, brief_id: int) -> JsonResponse:
    """JSON poll target while personalization runs."""
    brief = get_object_or_404(UserBrief, pk=brief_id, user=request.user)
    return JsonResponse(
        {
            "brief_id": brief.id,
            "status": brief.status,
            "error": brief.error if brief.status == UserBrief.Status.FAILED else "",
        }
    )


def _stories_feed_ids(request: HttpRequest) -> tuple[list[int], bool]:
    """Feed scope for Stories: enabled feeds when signed in, else English catalog."""
    if request.user.is_authenticated:
        return enabled_feed_ids(request.user), True
    return catalog_feed_ids(languages=set(DEFAULT_CONTENT_LANGUAGES)), False


def _parse_stories_since(raw: str | None) -> datetime | None:
    """Parse an ISO watermark from ?since=; invalid values are ignored."""
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def stories(request: HttpRequest) -> HttpResponse:
    """Importance-ranked catalog for guests; enabled feeds (mutes/custom) when signed in."""
    feed_ids, personalized = _stories_feed_ids(request)
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    since_raw = request.GET.get("since") or None
    since = _parse_stories_since(since_raw)
    feed_page = build_stories_feed_page(feed_ids, page=page, since=since)
    entries = feed_page.entries
    preferred_order = preferred_content_language_order(
        request.user if request.user.is_authenticated else None
    )
    for entry in entries:
        if entry.kind == "thread" and entry.thread is not None:
            lead_title = entry.lead_article.title if entry.lead_article is not None else ""
            apply_thread_display_copy(entry.thread, preferred_order, fallback_title=lead_title)
    has_new = any(entry.is_new for entry in entries)
    has_earlier = any(not entry.is_new for entry in entries)
    return render(
        request,
        "news/stories.html",
        {
            "entries": entries,
            "feed_count": len(feed_ids),
            "personalized": personalized,
            "feed_page": feed_page,
            "since": since_raw if since is not None else None,
            "show_new_heading": feed_page.since_active and has_new,
            "show_earlier_heading": feed_page.since_active and has_earlier,
            "separator_before_index": next(
                (i for i, entry in enumerate(entries) if not entry.is_new),
                None,
            )
            if feed_page.since_active and has_new and has_earlier
            else None,
        },
    )


def story_thread(request: HttpRequest, thread_id: int) -> HttpResponse:
    """Story thread detail with a chronological article timeline."""
    feed_ids, personalized = _stories_feed_ids(request)
    thread = thread_visible_in_scope(thread_id, feed_ids)
    if thread is None:
        raise Http404("Story thread not found.")
    articles = thread_timeline_articles(thread)
    preferred_order = preferred_content_language_order(
        request.user if request.user.is_authenticated else None
    )
    lead_title = articles[0].title if articles else ""
    apply_thread_display_copy(thread, preferred_order, fallback_title=lead_title)
    # Timeline is newest-first; date span still runs oldest → newest.
    first_published = articles[-1].published_at if articles else None
    last_published = articles[0].published_at if articles else None
    summary_open_cutoff = timezone.now() - timedelta(hours=24)
    return render(
        request,
        "news/story_thread.html",
        {
            "thread": thread,
            "articles": articles,
            "article_count": len(articles),
            "first_published": first_published,
            "last_published": last_published,
            "summary_open_cutoff": summary_open_cutoff,
            "personalized": personalized,
        },
    )


def _ensure_content_languages(user) -> set[str]:
    """Return preferred languages, creating the English default if missing."""
    preferred = preferred_content_languages(user)
    if not UserContentLanguage.objects.filter(user=user).exists():
        set_user_content_languages(user, languages=["en"], primary="en")
        preferred = set(DEFAULT_CONTENT_LANGUAGES)
    elif not UserContentLanguage.objects.filter(user=user, is_primary=True).exists():
        set_user_content_languages(
            user,
            languages=sorted(preferred),
            primary=primary_content_language(user),
        )
    return preferred


def _resolve_custom_feed(user, cleaned: dict) -> tuple[Feed, str]:
    """Create or attach a feed URL for the user; return (feed, flash message)."""
    url = cleaned["url"]
    existing = Feed.objects.filter(url=url).first()
    if existing is None:
        feed = Feed.objects.create(
            title=cleaned["title"],
            url=url,
            site_url=cleaned.get("site_url") or "",
            description=cleaned.get("description") or "",
            category=cleaned.get("category") or "Custom",
            kind=Feed.SourceKind.CUSTOM,
            language_id="und",
            owner=user,
            is_active=True,
        )
        Subscription.objects.get_or_create(user=user, feed=feed)
        return feed, f"Added “{feed.title}” (subscribed)."

    if existing.kind in {Feed.SourceKind.CURATED, Feed.SourceKind.RECOMMENDED}:
        FeedMute.objects.filter(user=user, feed=existing).delete()
        return existing, f"“{existing.title}” is in the catalog — enabled for you."

    Subscription.objects.get_or_create(user=user, feed=existing)
    return existing, f"Subscribed to “{existing.title}”."


@login_required
def settings_page(request: HttpRequest) -> HttpResponse:
    muted_ids = set(FeedMute.objects.filter(user=request.user).values_list("feed_id", flat=True))
    preferred = _ensure_content_languages(request.user)
    available_langs = catalog_languages() or ["en"]
    catalog = catalog_feeds()
    custom = Feed.objects.filter(
        kind=Feed.SourceKind.CUSTOM,
        is_active=True,
        subscriptions__user=request.user,
    ).distinct()
    recommended = recommend_feeds(request.user)
    locations = LocationOfInterest.objects.filter(user=request.user)
    # One-time hierarchy backfill for LOIs that only have coords/label.
    for loc in locations:
        if loc.country_code or loc.latitude is None or loc.longitude is None:
            continue
        place = reverse_geocode_place(loc.latitude, loc.longitude)
        if not place:
            continue
        loc.country_code = place.get("country_code") or ""
        loc.admin1 = place.get("admin1") or ""
        loc.locality = place.get("locality") or ""
        loc.geo_level = place.get("geo_level") or loc.geo_level
        if place.get("label"):
            loc.label = place["label"]
        loc.save(
            update_fields=[
                "country_code",
                "admin1",
                "locality",
                "geo_level",
                "label",
            ]
        )
    feed_form = CustomFeedForm()
    location_form = LocationOfInterestForm()
    user = cast(AbstractBaseUser, request.user)
    languages_form = ContentLanguagesForm(
        available=available_langs,
        initial={
            "languages": sorted(preferred),
            "primary": primary_content_language(user),
        },
    )

    if request.method == "POST" and "save_languages" in request.POST:
        languages_form = ContentLanguagesForm(request.POST, available=available_langs)
        if languages_form.is_valid():
            set_user_content_languages(
                user,
                languages=list(languages_form.cleaned_data["languages"]),
                primary=str(languages_form.cleaned_data["primary"]),
            )
            messages.success(request, _("Content languages updated."))
            return redirect("settings")

    if request.method == "POST" and "add_custom" in request.POST:
        feed_form = CustomFeedForm(request.POST)
        if feed_form.is_valid():
            _feed, msg = _resolve_custom_feed(request.user, feed_form.cleaned_data)
            messages.success(request, msg)
            return redirect("settings")

    if request.method == "POST" and "add_location" in request.POST:
        location_form = LocationOfInterestForm(request.POST)
        if location_form.is_valid():
            loc = location_form.save(commit=False)
            loc.user = request.user
            if loc.latitude is None or loc.longitude is None or not loc.country_code:
                hits = search_places(loc.label, limit=1)
                if hits:
                    hit = hits[0]
                    loc.latitude = hit["latitude"]
                    loc.longitude = hit["longitude"]
                    loc.label = hit["label"]
                    loc.country_code = hit.get("country_code") or ""
                    loc.admin1 = hit.get("admin1") or ""
                    loc.locality = hit.get("locality") or ""
                    loc.geo_level = hit.get("geo_level") or loc.geo_level
            loc.save()
            messages.success(request, f"Added location “{loc.label}”.")
            return redirect("settings")

    return render(
        request,
        "news/settings.html",
        {
            "catalog": catalog,
            "custom_feeds": custom,
            "recommended": recommended,
            "muted_ids": muted_ids,
            "preferred_languages": preferred,
            "language_labels": content_language_labels(),
            "languages_form": languages_form,
            "feed_form": feed_form,
            "location_form": location_form,
            "locations": locations,
        },
    )


@login_required
@require_POST
def mute_feed(request: HttpRequest, feed_id: int) -> HttpResponse:
    feed = get_object_or_404(Feed, pk=feed_id, is_active=True)
    if feed.kind == Feed.SourceKind.CUSTOM:
        messages.error(request, "Unsubscribe from custom feeds instead of muting.")
        return redirect("settings")
    FeedMute.objects.get_or_create(user=request.user, feed=feed)
    messages.info(request, f"Muted {feed.title}.")
    return redirect(request.POST.get("next") or "settings")


@login_required
@require_POST
def unmute_feed(request: HttpRequest, feed_id: int) -> HttpResponse:
    FeedMute.objects.filter(user=request.user, feed_id=feed_id).delete()
    feed = Feed.objects.filter(pk=feed_id).first()
    messages.success(request, f"Enabled {feed.title}." if feed else "Feed enabled.")
    return redirect(request.POST.get("next") or "settings")


@login_required
@require_POST
def unsubscribe_feed(request: HttpRequest, feed_id: int) -> HttpResponse:
    feed = get_object_or_404(Feed, pk=feed_id, kind=Feed.SourceKind.CUSTOM, is_active=True)
    deleted, _ = Subscription.objects.filter(user=request.user, feed=feed).delete()
    if deleted:
        messages.info(request, f"Unsubscribed from {feed.title}.")
    else:
        messages.info(request, "You were not subscribed to that feed.")
    return redirect(request.POST.get("next") or "settings")


def _request_lang(request: HttpRequest) -> str:
    return (request.GET.get("lang") or request.LANGUAGE_CODE or "en").strip()


@login_required
def geocode_reverse(request: HttpRequest) -> JsonResponse:
    """JSON: reverse-geocode lat/lng → hierarchical place for the location picker."""
    try:
        lat = float(request.GET.get("lat", ""))
        lng = float(request.GET.get("lng", ""))
    except (TypeError, ValueError):
        return JsonResponse({"error": "lat and lng required"}, status=400)
    place = reverse_geocode_place(lat, lng, lang=_request_lang(request))
    if not place:
        return JsonResponse(
            {
                "label": f"Near {lat:.2f}, {lng:.2f}",
                "latitude": lat,
                "longitude": lng,
                "country_code": "",
                "admin1": "",
                "locality": "",
                "geo_level": "locality",
            }
        )
    return JsonResponse(place)


@login_required
def geocode_search(request: HttpRequest) -> JsonResponse:
    """JSON: forward-geocode a place query for the location search box."""
    q = (request.GET.get("q") or "").strip()
    return JsonResponse({"results": search_places(q, limit=5, lang=_request_lang(request))})


@login_required
@require_POST
def delete_location(request: HttpRequest, location_id: int) -> HttpResponse:
    deleted, _ = LocationOfInterest.objects.filter(user=request.user, pk=location_id).delete()
    if deleted:
        messages.info(request, "Location removed.")
    return redirect(request.POST.get("next") or "settings")


@login_required
def stored_preferences(request: HttpRequest) -> JsonResponse:
    """JSON: AgentCore memories + theme leanings for the Settings modal."""
    user = cast(AbstractBaseUser, request.user)
    memories = list_preference_memories(int(user.pk))
    themes = [
        {
            "slug": row.theme.slug,
            "label": row.theme.label,
            "more_count": row.more_count,
            "less_count": row.less_count,
        }
        for row in affinities_for_user(user)
    ]
    return JsonResponse({"ok": True, "memories": memories, "themes": themes})


@login_required
@require_POST
def delete_stored_memory(request: HttpRequest) -> HttpResponse:
    user = cast(AbstractBaseUser, request.user)
    record_id = (request.POST.get("record_id") or "").strip()
    if not record_id:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        record_id = str(body.get("record_id") or "").strip()
    if not record_id:
        return JsonResponse({"ok": False, "error": "Missing record_id."}, status=400)
    ok = delete_preference_memory(int(user.pk), record_id)
    if not ok:
        return JsonResponse({"ok": False, "error": "Could not delete memory."}, status=502)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def delete_theme_leaning(request: HttpRequest) -> HttpResponse:
    user = cast(AbstractBaseUser, request.user)
    slug = (request.POST.get("theme") or "").strip()
    if not slug:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        slug = str(body.get("theme") or "").strip()
    if not slug:
        return JsonResponse({"ok": False, "error": "Missing theme."}, status=400)
    if not delete_theme_affinity(user, theme_slug=slug):
        return JsonResponse({"ok": False, "error": "Theme leaning not found."}, status=404)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def feedback(request: HttpRequest, article_id: int) -> HttpResponse:
    user = cast(AbstractBaseUser, request.user)
    article = get_object_or_404(Article, pk=article_id)
    verdict = request.POST.get("verdict")
    allowed = {c.value for c in RelevanceFeedback.Verdict}
    wants_json = request.headers.get(
        "X-Requested-With"
    ) == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or "")
    if verdict not in allowed:
        if wants_json:
            return JsonResponse({"ok": False, "error": "Unknown feedback action."}, status=400)
        messages.error(request, "Unknown feedback action.")
        return redirect("brief")

    RelevanceFeedback.objects.update_or_create(
        user=user,
        article=article,
        defaults={"verdict": verdict},
    )
    # Theme chips + brief chat own AgentCore writes; verdicts only dismiss.
    labels: dict[str, str] = {
        RelevanceFeedback.Verdict.RELEVANT.value: "Marked as relevant",
        RelevanceFeedback.Verdict.NOT_RELEVANT.value: "Marked as not relevant",
        RelevanceFeedback.Verdict.SKIP.value: "Skipped",
    }
    message = labels[verdict]
    if wants_json:
        return JsonResponse(
            {"ok": True, "verdict": verdict, "message": message, "article_id": article.id}
        )
    messages.success(request, message)
    return redirect("brief")


@login_required
@require_POST
def theme_affinity(request: HttpRequest, article_id: int) -> HttpResponse:
    """Apply more/less lean for a theme on a brief article (no AgentCore)."""
    user = cast(AbstractBaseUser, request.user)
    article = get_object_or_404(Article.objects.prefetch_related("themes"), pk=article_id)
    slug = (request.POST.get("theme") or "").strip()
    direction = (request.POST.get("direction") or "").strip()
    previous = (request.POST.get("previous") or "neutral").strip() or "neutral"
    wants_json = request.headers.get(
        "X-Requested-With"
    ) == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or "")
    if direction not in ("more", "less"):
        if wants_json:
            return JsonResponse({"ok": False, "error": "Unknown direction."}, status=400)
        messages.error(request, "Unknown theme action.")
        return redirect("brief")
    if previous not in ("more", "less", "neutral"):
        if wants_json:
            return JsonResponse({"ok": False, "error": "Unknown previous lean."}, status=400)
        messages.error(request, "Unknown theme action.")
        return redirect("brief")
    article_slugs = {t.slug for t in article.themes.all()}
    if slug not in article_slugs:
        if wants_json:
            return JsonResponse({"ok": False, "error": "Theme not on this article."}, status=400)
        messages.error(request, "Theme not on this article.")
        return redirect("brief")
    lean_direction: AffinityDirection = "more" if direction == "more" else "less"
    lean_previous: AffinityLean = previous  # narrowed by membership check above
    affinity = apply_theme_affinity_vote(
        user,
        theme_slug=slug,
        direction=lean_direction,
        previous=lean_previous,
    )
    if affinity is None:
        if wants_json:
            return JsonResponse({"ok": False, "error": "Unknown theme."}, status=400)
        messages.error(request, "Unknown theme.")
        return redirect("brief")
    label = affinity.theme.label
    message = f"More {label}" if direction == "more" else f"Less {label}"
    if wants_json:
        return JsonResponse(
            {
                "ok": True,
                "theme": slug,
                "direction": direction,
                "previous": previous,
                "message": message,
                "more_count": affinity.more_count,
                "less_count": affinity.less_count,
            }
        )
    messages.success(request, message)
    return redirect("brief")


def _parse_chat_json(request: HttpRequest) -> dict[str, Any] | None:
    try:
        raw = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _chat(request: HttpRequest) -> JsonResponse:
    """JSON chat endpoint: rate-limit → retrieve → invoke news_chat worker."""
    # @login_required guarantees an authenticated user; stubs still type AnonymousUser.
    user = cast(AbstractBaseUser, request.user)
    payload = _parse_chat_json(request)
    if payload is None:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    scope = (payload.get("scope") or "").strip()
    if scope not in ("brief", "thread"):
        return JsonResponse({"ok": False, "error": "scope must be brief or thread."}, status=400)

    scope_id_raw = payload.get("scope_id")
    scope_id: int | None
    if scope_id_raw is None or scope_id_raw == "":
        scope_id = None
    else:
        try:
            scope_id = int(scope_id_raw)
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Invalid scope_id."}, status=400)

    if scope == "thread" and scope_id is None:
        return JsonResponse({"ok": False, "error": "scope_id required for thread."}, status=400)

    message = (payload.get("message") or "").strip()
    if not message:
        return JsonResponse({"ok": False, "error": "message is required."}, status=400)
    if len(message) > MAX_MESSAGE_CHARS:
        return JsonResponse(
            {"ok": False, "error": f"message exceeds {MAX_MESSAGE_CHARS} characters."},
            status=400,
        )

    history_raw = payload.get("history") or []
    if not isinstance(history_raw, list):
        return JsonResponse({"ok": False, "error": "history must be a list."}, status=400)
    if len(history_raw) > MAX_HISTORY_TURNS:
        return JsonResponse(
            {"ok": False, "error": f"history exceeds {MAX_HISTORY_TURNS} turns."},
            status=400,
        )

    try:
        history = [ChatHistoryMessage.model_validate(item) for item in history_raw]
    except ValidationError:
        return JsonResponse({"ok": False, "error": "Invalid history entries."}, status=400)

    decision = check_and_increment(user)
    if not decision.allowed:
        response = JsonResponse(
            {
                "ok": False,
                "error": decision.detail,
                "code": "rate_limited",
            },
            status=429,
        )
        response["Retry-After"] = str(decision.retry_after_seconds)
        return response

    chunks = retrieve(scope=scope, user=user, scope_id=scope_id)
    if chunks is None:
        return JsonResponse({"ok": False, "error": "Story thread not found."}, status=404)

    try:
        worker_req = ChatWorkerRequest(
            scope=scope,  # type: ignore[arg-type]
            scope_id=scope_id,
            user_id=int(user.pk),
            message=message,
            history=history,
            chunks=chunks,
        )
    except ValidationError:
        return JsonResponse({"ok": False, "error": "Invalid chat request."}, status=400)

    result = invoke_news_chat(worker_req)
    if result.refused:
        return JsonResponse(
            {
                "ok": True,
                "refused": True,
                "reason": result.reason,
                "reply": result.message or result.reply,
                "citations": [],
            }
        )
    return JsonResponse(
        {
            "ok": True,
            "refused": False,
            "reason": "ok",
            "reply": result.reply,
            "citations": [c.model_dump() for c in result.citations],
        }
    )


# django-stubs decorator overloads disagree with JsonResponse views (same as other views).
_login_required = cast(Any, login_required)
chat = _login_required(require_POST(cast(Any, _chat)))
