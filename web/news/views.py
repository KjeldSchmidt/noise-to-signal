from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from news.forms import CustomFeedForm, FollowUpAnswerForm, LocationOfInterestForm
from news.models import (
    Article,
    Feed,
    FeedMute,
    FollowUpAnswer,
    FollowUpQuestion,
    LocationOfInterest,
    RelevanceFeedback,
)
from news.services import (
    catalog_feed_ids,
    catalog_feeds,
    enabled_feed_ids,
    next_questions,
    rank_items,
    recommend_feeds,
)
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


def stories(request: HttpRequest) -> HttpResponse:
    """Non-personalized catalog for guests; enabled feeds (mutes/custom) when signed in."""
    personalized = request.user.is_authenticated
    feed_ids = (
        enabled_feed_ids(request.user) if personalized else catalog_feed_ids()
    )
    articles = (
        Article.objects.filter(feed_id__in=feed_ids)
        .select_related("feed")
        .order_by("-published_at")[:40]
    )
    return render(
        request,
        "news/stories.html",
        {
            "articles": articles,
            "feed_count": len(feed_ids),
            "personalized": personalized,
        },
    )


@login_required
def settings_page(request: HttpRequest) -> HttpResponse:
    muted_ids = set(
        FeedMute.objects.filter(user=request.user).values_list("feed_id", flat=True)
    )
    catalog = catalog_feeds()
    custom = Feed.objects.filter(owner=request.user, is_active=True)
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

    if request.method == "POST" and "add_custom" in request.POST:
        feed_form = CustomFeedForm(request.POST)
        if feed_form.is_valid():
            feed = Feed.objects.create(
                title=feed_form.cleaned_data["title"],
                url=feed_form.cleaned_data["url"],
                site_url=feed_form.cleaned_data.get("site_url") or "",
                description=feed_form.cleaned_data.get("description") or "",
                category=feed_form.cleaned_data.get("category") or "Custom",
                kind=Feed.SourceKind.CUSTOM,
                owner=request.user,
            )
            messages.success(request, f"Added “{feed.title}” (enabled for you).")
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
            "feed_form": feed_form,
            "location_form": location_form,
            "locations": locations,
        },
    )


@login_required
@require_POST
def mute_feed(request: HttpRequest, feed_id: int) -> HttpResponse:
    feed = get_object_or_404(Feed, pk=feed_id, is_active=True)
    if feed.owner_id and feed.owner_id != request.user.id:
        messages.error(request, "That feed is private to another user.")
        return redirect("settings")
    FeedMute.objects.get_or_create(user=request.user, feed=feed)
    messages.info(request, f"Muted {feed.title}.")
    return redirect(request.POST.get("next") or "settings")


@login_required
@require_POST
def unmute_feed(request: HttpRequest, feed_id: int) -> HttpResponse:
    FeedMute.objects.filter(user=request.user, feed_id=feed_id).delete()
    feed = Feed.objects.filter(pk=feed_id).first()
    messages.success(
        request, f"Enabled {feed.title}." if feed else "Feed enabled."
    )
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
    return JsonResponse(
        {"results": search_places(q, limit=5, lang=_request_lang(request))}
    )


@login_required
@require_POST
def delete_location(request: HttpRequest, location_id: int) -> HttpResponse:
    deleted, _ = LocationOfInterest.objects.filter(
        user=request.user, pk=location_id
    ).delete()
    if deleted:
        messages.info(request, "Location removed.")
    return redirect("settings")


@login_required
@require_POST
def feedback(request: HttpRequest, article_id: int) -> HttpResponse:
    article = get_object_or_404(Article, pk=article_id)
    verdict = request.POST.get("verdict")
    allowed = {c.value for c in RelevanceFeedback.Verdict}
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )
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
        existing = FollowUpAnswer.objects.filter(
            user=request.user, question=question
        ).first()
        form = FollowUpAnswerForm(instance=existing)
    return render(
        request,
        "news/answer_followup.html",
        {"question": question, "form": form},
    )
