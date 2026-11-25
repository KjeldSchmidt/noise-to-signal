"""Build candidate + user-context payloads for the brief_builder worker."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.http import Http404
from n2s_api import (
    BriefCandidateDTO,
    BriefLocationDTO,
    BriefThemeAffinityDTO,
    BriefUserContextResponse,
)

from news.models import Article, LocationOfInterest, RelevanceFeedback
from news.services.brief import CANDIDATE_LIMIT
from news.services.feeds import enabled_feed_ids, preferred_content_languages
from news.services.stories_feed import build_stories_feed
from news.services.theme_affinity import affinities_for_user, affinity_weight

User = get_user_model()

_THREAD_THEME_CAP = 6


def _member_ids_by_thread(thread_ids: list[int]) -> dict[int, list[int]]:
    if not thread_ids:
        return {}
    out: dict[int, list[int]] = {tid: [] for tid in thread_ids}
    for article_id, thread_id in (
        Article.objects.filter(story_thread_id__in=thread_ids)
        .values_list("id", "story_thread_id")
        .iterator()
    ):
        if thread_id is None:
            continue
        out.setdefault(thread_id, []).append(int(article_id))
    return out


def _themes_for_articles(article_ids: list[int], *, limit: int = _THREAD_THEME_CAP) -> list[str]:
    if not article_ids:
        return []
    slugs: list[str] = []
    seen: set[str] = set()
    for slug in (
        Article.objects.filter(id__in=article_ids)
        .values_list("themes__slug", flat=True)
        .order_by("themes__slug")
    ):
        if not slug or slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
        if len(slugs) >= limit:
            break
    return slugs


def build_brief_user_context(user_id: int) -> BriefUserContextResponse:
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise Http404("user not found") from exc

    feed_ids = enabled_feed_ids(user)
    judged = set(RelevanceFeedback.objects.filter(user=user).values_list("article_id", flat=True))
    entries = build_stories_feed(feed_ids, limit=CANDIDATE_LIMIT * 2) if feed_ids else []

    thread_ids = [
        entry.thread.id for entry in entries if entry.kind == "thread" and entry.thread is not None
    ]
    members_by_thread = _member_ids_by_thread(thread_ids)

    candidates: list[BriefCandidateDTO] = []
    for entry in entries:
        if entry.kind == "article" and entry.article is not None:
            article = entry.article
            if article.id in judged:
                continue
            themes = list(article.themes.values_list("slug", flat=True)[:_THREAD_THEME_CAP])
            candidates.append(
                BriefCandidateDTO(
                    kind="article",
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
                    article_count=1,
                )
            )
        elif entry.kind == "thread" and entry.thread is not None and entry.lead_article is not None:
            thread = entry.thread
            lead = entry.lead_article
            member_ids = members_by_thread.get(thread.id, [])
            if any(mid in judged for mid in member_ids):
                continue
            summary = (thread.summary or lead.summary or "")[:800]
            source_titles = [f.title for f in entry.source_feeds[:4]]
            source = (
                f"{len(entry.source_feeds)} sources"
                if len(entry.source_feeds) > 1
                else (source_titles[0] if source_titles else "")
            )
            candidates.append(
                BriefCandidateDTO(
                    kind="thread",
                    article_id=lead.id,
                    story_thread_id=thread.id,
                    title=(thread.label or lead.title)[:300],
                    url=lead.url,
                    summary=summary,
                    source=source,
                    published_at=thread.last_published_at.isoformat(),
                    impact_tier=lead.impact_tier or "",
                    story_label=thread.label or lead.story_label or "",
                    place_label=lead.place_label or "",
                    country_code=lead.country_code or "",
                    themes=_themes_for_articles(member_ids),
                    score=round(float(entry.score), 4),
                    article_count=max(entry.article_count, len(member_ids), 2),
                )
            )
        else:
            continue
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

    theme_affinities = [
        BriefThemeAffinityDTO(
            slug=row.theme.slug,
            label=row.theme.label,
            more_count=row.more_count,
            less_count=row.less_count,
            weight=round(affinity_weight(row.more_count, row.less_count), 4),
        )
        for row in affinities_for_user(user)
    ]

    return BriefUserContextResponse(
        user_id=user_id,
        languages=list(preferred_content_languages(user)),
        locations=locations,
        theme_affinities=theme_affinities,
        candidates=candidates,
    )


def user_for_brief(user_id: int) -> AbstractBaseUser:
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise Http404("user not found") from exc
