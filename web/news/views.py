import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AbstractBaseUser
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from n2s_api import (
    MAX_HISTORY_TURNS,
    MAX_MESSAGE_CHARS,
    ChatHistoryMessage,
    ChatWorkerRequest,
)
from pydantic import ValidationError

from news.forms import (
    ContentLanguagesForm,
    CustomFeedForm,
    FollowUpAnswerForm,
    LocationOfInterestForm,
)
from news.models import (
    Article,
    Feed,
    FeedMute,
    FollowUpAnswer,
    FollowUpQuestion,
    LocationOfInterest,
    RelevanceFeedback,
    Subscription,
    UserContentLanguage,
)
from news.services import (
    CONTENT_LANGUAGE_LABELS,
    DEFAULT_CONTENT_LANGUAGES,
    build_stories_feed_page,
    catalog_feed_ids,
    catalog_feeds,
    catalog_languages,
    enabled_feed_ids,
    next_questions,
    preferred_content_languages,
    rank_items,
    recommend_feeds,
    thread_timeline_articles,
    thread_visible_in_scope,
)
from news.services.chat_invoke import invoke_news_chat
from news.services.chat_rate_limit import check_and_increment
from news.services.chat_retrieve import retrieve
from news.services.geocode import reverse_geocode_place, search_places


def landing(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("brief")
    # Ensure a session cookie exists before the OAuth popup opens (same-site share).
    request.session.setdefault("oauth_ready", True)
    return render(request, "news/landing.html")


@login_required
def oauth_popup_done(request: HttpRequest) -> HttpResponse:
    """Land here after Google OAuth in a popup; close popup and navigate opener."""
    return render(
        request,
        "news/oauth_popup_done.html",
        {"next_url": request.GET.get("next") or reverse("brief")},
    )


@login_required
def brief(request: HttpRequest) -> HttpResponse:
    ranked = rank_items(request.user)
    pending_questions = next_questions(request.user, limit=1)
    feed_count = len(enabled_feed_ids(request.user))
    return render(
        request,
        "news/brief.html",
        {
            "ranked": ranked,
            "pending_question": pending_questions[0] if pending_questions else None,
            "feed_count": feed_count,
        },
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
        UserContentLanguage.objects.get_or_create(user=user, language="en")
        preferred = set(DEFAULT_CONTENT_LANGUAGES)
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
            language="und",
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
    languages_form = ContentLanguagesForm(
        available=available_langs,
        initial={"languages": sorted(preferred)},
    )

    if request.method == "POST" and "save_languages" in request.POST:
        languages_form = ContentLanguagesForm(request.POST, available=available_langs)
        if languages_form.is_valid():
            selected = [
                str(code).strip().lower() for code in languages_form.cleaned_data["languages"]
            ]
            if not selected:
                selected = ["en"]
            UserContentLanguage.objects.filter(user=request.user).exclude(
                language__in=selected
            ).delete()
            for code in selected:
                UserContentLanguage.objects.get_or_create(user=request.user, language=code)
            messages.success(request, "Content languages updated.")
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
            "language_labels": CONTENT_LANGUAGE_LABELS,
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
    return redirect("settings")


@login_required
@require_POST
def feedback(request: HttpRequest, article_id: int) -> HttpResponse:
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
        user=request.user,
        article=article,
        defaults={"verdict": verdict},
    )
    labels = {
        RelevanceFeedback.Verdict.RELEVANT: "Marked as relevant",
        RelevanceFeedback.Verdict.NOT_RELEVANT: "Marked as not relevant",
        RelevanceFeedback.Verdict.SKIP: "Skipped",
    }
    message = labels[verdict]
    if wants_json:
        return JsonResponse(
            {"ok": True, "verdict": verdict, "message": message, "article_id": article.id}
        )
    messages.success(request, message)
    return redirect("brief")


@login_required
def followups(request: HttpRequest) -> HttpResponse:
    questions = next_questions(request.user, limit=5)
    answered = (
        FollowUpAnswer.objects.filter(user=request.user)
        .select_related("question")
        .order_by("-updated_at")
    )
    return render(
        request,
        "news/followups.html",
        {"questions": questions, "answered": answered},
    )


@login_required
def answer_followup(request: HttpRequest, question_id: int) -> HttpResponse:
    question = get_object_or_404(FollowUpQuestion, pk=question_id, is_active=True)
    if request.method == "POST":
        form = FollowUpAnswerForm(request.POST)
        if form.is_valid():
            FollowUpAnswer.objects.update_or_create(
                user=request.user,
                question=question,
                defaults={"answer": form.cleaned_data["answer"]},
            )
            messages.success(request, "Saved — that will shape future filtering.")
            return redirect("followups")
    else:
        existing = FollowUpAnswer.objects.filter(user=request.user, question=question).first()
        form = FollowUpAnswerForm(instance=existing)
    return render(
        request,
        "news/answer_followup.html",
        {"question": question, "form": form},
    )


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
            }
        )
    return JsonResponse(
        {
            "ok": True,
            "refused": False,
            "reason": "ok",
            "reply": result.reply,
        }
    )


# django-stubs decorator overloads disagree with JsonResponse views (same as other views).
_login_required = cast(Any, login_required)
chat = _login_required(require_POST(cast(Any, _chat)))
