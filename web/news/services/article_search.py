"""Feed-scoped article search by title/summary text and embedding similarity."""

from __future__ import annotations

from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import connection
from django.db.models import Q, QuerySet
from django.utils import timezone
from n2s_api import MAX_CHUNKS, ContextChunk

from news.models import Article
from news.services.chat_retrieve import article_to_chunk
from news.services.feeds import enabled_feed_ids
from news.services.impact import blend_relevance_impact, score_article
from news.services.threading import cosine_similarity

User = get_user_model()

# Minimum cosine similarity for ANN hits (clustering vectors). Tune with real queries.
MIN_EMBEDDING_SIMILARITY = 0.60


def _parse_published_after(value: str | datetime | None) -> datetime | None:
    """Parse an ISO published_after bound; return None when unset or invalid."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value, UTC)
        return value
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, UTC)
    return parsed


def _scoped_articles(
    user: AbstractBaseUser,
    *,
    country_code: str | None = None,
    published_after: datetime | None = None,
) -> QuerySet[Article]:
    feed_ids = enabled_feed_ids(user)
    if not feed_ids:
        return Article.objects.none()
    qs = Article.objects.filter(feed_id__in=feed_ids).select_related("feed")
    code = (country_code or "").strip().lower()[:2]
    if code:
        qs = qs.filter(country_code__iexact=code)
    if published_after is not None:
        qs = qs.filter(published_at__gte=published_after)
    return qs


def _title_hits(
    qs: QuerySet[Article],
    *,
    query: str,
    exclude_ids: set[int],
    limit: int,
) -> list[Article]:
    if limit < 1:
        return []
    filtered = qs.exclude(pk__in=exclude_ids).filter(
        Q(title__icontains=query) | Q(summary__icontains=query)
    )
    return list(filtered.order_by("-published_at")[:limit])


def _embedding_hits_postgres(
    qs: QuerySet[Article],
    *,
    embedding: list[float],
    exclude_ids: set[int],
    limit: int,
    min_similarity: float,
) -> list[tuple[Article, float]]:
    from pgvector.django import CosineDistance

    if limit < 1:
        return []
    max_distance = 1.0 - min_similarity
    ranked = (
        qs.exclude(pk__in=exclude_ids)
        .exclude(embedding__isnull=True)
        .annotate(distance=CosineDistance("embedding", embedding))
        .filter(distance__lte=max_distance)
        .order_by("distance")[:limit]
    )
    out: list[tuple[Article, float]] = []
    for article in ranked:
        distance = float(getattr(article, "distance", 1.0))
        similarity = max(0.0, min(1.0, 1.0 - distance))
        out.append((article, similarity))
    return out


def _embedding_hits_python(
    qs: QuerySet[Article],
    *,
    embedding: list[float],
    exclude_ids: set[int],
    limit: int,
    min_similarity: float,
) -> list[tuple[Article, float]]:
    """SQLite / non-pgvector path: brute-force cosine over scoped rows."""
    if limit < 1:
        return []
    candidates = list(
        qs.exclude(pk__in=exclude_ids).exclude(embedding__isnull=True).iterator(chunk_size=200)
    )
    scored: list[tuple[float, Article]] = []
    for article in candidates:
        sim = cosine_similarity(list(article.embedding), embedding)
        if sim >= min_similarity:
            scored.append((sim, article))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [(article, sim) for sim, article in scored[:limit]]


def _embedding_hits(
    qs: QuerySet[Article],
    *,
    embedding: list[float],
    exclude_ids: set[int],
    limit: int,
    min_similarity: float = MIN_EMBEDDING_SIMILARITY,
) -> list[tuple[Article, float]]:
    if connection.vendor == "postgresql":
        return _embedding_hits_postgres(
            qs,
            embedding=embedding,
            exclude_ids=exclude_ids,
            limit=limit,
            min_similarity=min_similarity,
        )
    return _embedding_hits_python(
        qs,
        embedding=embedding,
        exclude_ids=exclude_ids,
        limit=limit,
        min_similarity=min_similarity,
    )


def _score_title_hit(
    article: Article,
    *,
    embedding: list[float] | None,
) -> float | None:
    """Optional similarity for title hits when a query embedding is available."""
    if embedding is None or article.embedding is None:
        return None
    return cosine_similarity(list(article.embedding), embedding)


def search_articles_for_user(
    *,
    user: AbstractBaseUser,
    query: str,
    embedding: list[float] | None = None,
    limit: int = 10,
    exclude_article_ids: list[int] | None = None,
    min_similarity: float = MIN_EMBEDDING_SIMILARITY,
    now: datetime | None = None,
    country_code: str | None = None,
    published_after: str | datetime | None = None,
) -> list[ContextChunk]:
    """
    Merge title/summary matches with embedding nearest neighbors.

    Title hits are preferred for recall; ANN fills remaining slots only when
    cosine similarity >= ``min_similarity``. Final order is relevance × impact
    (decayed tier weight). Chunks still expose raw ``similarity`` when known.

    Optional ``country_code`` / ``published_after`` narrow the feed-scoped set
    before title and ANN matching.
    """
    capped = max(1, min(limit, MAX_CHUNKS))
    exclude = set(exclude_article_ids or [])
    qs = _scoped_articles(
        user,
        country_code=country_code,
        published_after=_parse_published_after(published_after),
    )
    if not qs.exists():
        return []

    clock = now or timezone.now()
    # Oversample then re-rank so a high-impact neighbor can displace fluff.
    fetch_cap = min(MAX_CHUNKS, max(capped * 3, capped))
    title_articles = _title_hits(qs, query=query, exclude_ids=exclude, limit=fetch_cap)
    ranked: list[tuple[float, ContextChunk]] = []
    for article in title_articles:
        similarity = _score_title_hit(article, embedding=embedding)
        chunk = article_to_chunk(article, similarity=similarity)
        ranked.append(
            (
                blend_relevance_impact(
                    similarity=similarity,
                    impact=score_article(article, now=clock),
                ),
                chunk,
            )
        )
    seen = {a.pk for a in title_articles} | exclude
    remaining = fetch_cap - len(title_articles)

    if embedding is not None and remaining > 0:
        for article, similarity in _embedding_hits(
            qs,
            embedding=embedding,
            exclude_ids=seen,
            limit=remaining,
            min_similarity=min_similarity,
        ):
            chunk = article_to_chunk(article, similarity=similarity)
            ranked.append(
                (
                    blend_relevance_impact(
                        similarity=similarity,
                        impact=score_article(article, now=clock),
                    ),
                    chunk,
                )
            )

    ranked.sort(key=lambda row: row[0], reverse=True)
    return [chunk for _, chunk in ranked[:capped]]


def search_articles_by_user_id(
    *,
    user_id: int,
    query: str,
    embedding: list[float] | None = None,
    limit: int = 10,
    exclude_article_ids: list[int] | None = None,
    min_similarity: float = MIN_EMBEDDING_SIMILARITY,
    country_code: str | None = None,
    published_after: str | datetime | None = None,
) -> list[ContextChunk] | None:
    """Resolve user by id; return None when the user does not exist."""
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return None
    return search_articles_for_user(
        user=user,
        query=query,
        embedding=embedding,
        limit=limit,
        exclude_article_ids=exclude_article_ids,
        min_similarity=min_similarity,
        country_code=country_code,
        published_after=published_after,
    )
