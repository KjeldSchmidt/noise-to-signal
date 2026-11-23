"""Build candidate + user-context payloads for the brief_builder worker."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.http import Http404
from n2s_api import (
    BriefCandidateDTO,
    BriefFeedbackDTO,
    BriefLocationDTO,
    BriefTasteDTO,
    BriefUserContextResponse,
)

from news.models import FollowUpAnswer, LocationOfInterest, RelevanceFeedback
from news.services.brief import CANDIDATE_LIMIT
from news.services.feeds import enabled_feed_ids, preferred_content_languages
from news.services.stories_feed import build_stories_feed

User = get_user_model()


def build_brief_user_context(user_id: int) -> BriefUserContextResponse:
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise Http404("user not found") from exc

    feed_ids = enabled_feed_ids(user)
    judged = set(RelevanceFeedback.objects.filter(user=user).values_list("article_id", flat=True))
    entries = build_stories_feed(feed_ids, limit=CANDIDATE_LIMIT * 2) if feed_ids else []

    candidates: list[BriefCandidateDTO] = []
    for entry in entries:
        article = entry.article if entry.kind == "article" else entry.lead_article
        if article is None or article.id in judged:
            continue
        # Ensure themes are loaded when possible
        themes = list(article.themes.values_list("slug", flat=True))
        candidates.append(
            BriefCandidateDTO(
                article_id=article.id,
                title=article.title,
                url=article.url,
                summary=(article.summary or "")[:800],
                source=article.feed.title if article.feed_id else "",
                published_at=article.published_at.isoformat(),
                impact_tier=article.impact_tier or "",
                story_label=article.story_label or "",
                place_label=article.place_label or "",
                country_code=article.country_code or "",
                themes=themes,
                score=round(float(entry.score), 4),
            )
        )
        if len(candidates) >= CANDIDATE_LIMIT:
            break

    locations = [
        BriefLocationDTO(
            label=loc.label,
            country_code=loc.country_code or "",
            admin1=loc.admin1 or "",
            locality=loc.locality or "",
            geo_level=loc.geo_level or "",
        )
        for loc in LocationOfInterest.objects.filter(user=user).order_by("id")
    ]

    taste = [
        BriefTasteDTO(question=a.question.prompt, answer=a.answer)
        for a in FollowUpAnswer.objects.filter(user=user)
        .select_related("question")
        .order_by("-updated_at")[:20]
    ]

    feedback = [
        BriefFeedbackDTO(
            article_id=fb.article_id,
            title=fb.article.title,
            verdict=fb.verdict,
        )
        for fb in RelevanceFeedback.objects.filter(user=user)
        .select_related("article")
        .order_by("-created_at")[:30]
    ]

    return BriefUserContextResponse(
        user_id=user_id,
        languages=list(preferred_content_languages(user)),
        locations=locations,
        taste_answers=taste,
        recent_feedback=feedback,
        candidates=candidates,
    )


def user_for_brief(user_id: int) -> AbstractBaseUser:
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise Http404("user not found") from exc
