"""Feed-scoped article search by title/summary text and embedding similarity."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import connection
from django.db.models import Q, QuerySet
from n2s_api import MAX_CHUNKS, ContextChunk

from news.models import Article
from news.services.chat_retrieve import article_to_chunk
from news.services.feeds import enabled_feed_ids
from news.services.threading import cosine_similarity

User = get_user_model()


def _scoped_articles(user: AbstractBaseUser) -> QuerySet[Article]:
    feed_ids = enabled_feed_ids(user)
    if not feed_ids:
        return Article.objects.none()
    return Article.objects.filter(feed_id__in=feed_ids).select_related("feed")


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
) -> list[Article]:
    from pgvector.django import CosineDistance

    if limit < 1:
        return []
    ranked = (
        qs.exclude(pk__in=exclude_ids)
        .exclude(embedding__isnull=True)
        .annotate(distance=CosineDistance("embedding", embedding))
        .order_by("distance")[:limit]
    )
    return list(ranked)


def _embedding_hits_python(
    qs: QuerySet[Article],
    *,
    embedding: list[float],
    exclude_ids: set[int],
    limit: int,
) -> list[Article]:
    """SQLite / non-pgvector path: brute-force cosine over scoped rows."""
    if limit < 1:
        return []
    candidates = list(
        qs.exclude(pk__in=exclude_ids).exclude(embedding__isnull=True).iterator(chunk_size=200)
    )
    scored: list[tuple[float, Article]] = []
    for article in candidates:
        sim = cosine_similarity(list(article.embedding), embedding)
        if sim > 0:
            scored.append((sim, article))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [article for _, article in scored[:limit]]


def _embedding_hits(
    qs: QuerySet[Article],
    *,
    embedding: list[float],
    exclude_ids: set[int],
    limit: int,
) -> list[Article]:
    if connection.vendor == "postgresql":
        return _embedding_hits_postgres(
            qs, embedding=embedding, exclude_ids=exclude_ids, limit=limit
        )
    return _embedding_hits_python(qs, embedding=embedding, exclude_ids=exclude_ids, limit=limit)


def search_articles_for_user(
    *,
    user: AbstractBaseUser,
    query: str,
    embedding: list[float] | None = None,
    limit: int = 10,
    exclude_article_ids: list[int] | None = None,
) -> list[ContextChunk]:
    """
    Merge title/summary matches with embedding nearest neighbors.

    Title hits are preferred in the merged ranking; vector hits fill remaining slots.
    """
    capped = max(1, min(limit, MAX_CHUNKS))
    exclude = set(exclude_article_ids or [])
    qs = _scoped_articles(user)
    if not qs.exists():
        return []

    title_articles = _title_hits(qs, query=query, exclude_ids=exclude, limit=capped)
    seen = {a.pk for a in title_articles} | exclude
    remaining = capped - len(title_articles)

    vector_articles: list[Article] = []
    if embedding is not None and remaining > 0:
        vector_articles = _embedding_hits(
            qs, embedding=embedding, exclude_ids=seen, limit=remaining
        )

    merged = title_articles + vector_articles
    return [article_to_chunk(a) for a in merged]


def search_articles_by_user_id(
    *,
    user_id: int,
    query: str,
    embedding: list[float] | None = None,
    limit: int = 10,
    exclude_article_ids: list[int] | None = None,
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
    )
