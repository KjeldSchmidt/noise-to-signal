"""Near-duplicate detection and story-thread assignment from article embeddings.

Story threads emerge only when two+ related articles connect. Lonely articles
stay unthreaded.

SCALING HOTSPOT: assignment takes a global Postgres advisory lock
(`STORY_ASSIGN_ADVISORY_LOCK_KEY` / `pg_advisory_xact_lock`). That serializes
story linking across concurrent upserts so related articles do not miss each
other. Bedrock embed/extract still run in parallel on workers. Fine at current
volume; under heavy concurrent upserts this may queue Lambda/API work. Prefer
faster peer queries, async reconcile, or a seeker job before removing the lock.
Search the repo for ``SCALING HOTSPOT`` to find this again.
"""

from __future__ import annotations

import math
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from news.models import Article, StoryThread

# Cosine similarity thresholds (Cohere vectors are typically L2-normalized).
DEDUP_SIMILARITY = 0.92
THREAD_SIMILARITY = 0.78
DEDUP_WINDOW = timedelta(hours=48)
THREAD_ACTIVE_WINDOW = timedelta(days=45)
CENTROID_EMA_ALPHA = 0.35

# SCALING HOTSPOT — global serialize of story linking (see module docstring).
STORY_ASSIGN_ADVISORY_LOCK_KEY = 874_201_339


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def _as_list(vector) -> list[float] | None:
    if vector is None:
        return None
    return [float(x) for x in vector]


def _ema_centroid(old, new: list[float], alpha: float = CENTROID_EMA_ALPHA) -> list[float]:
    prev = _as_list(old)
    if not prev or len(prev) != len(new):
        return list(new)
    return [((1.0 - alpha) * o) + (alpha * n) for o, n in zip(prev, new, strict=True)]


def _story_label_for(*articles: Article) -> str:
    for article in articles:
        label = (getattr(article, "story_label", None) or "").strip()
        if label:
            return label[:300]
    return ""


def _acquire_story_assign_lock() -> None:
    """SCALING HOTSPOT: pg_advisory_xact_lock for story assignment (Postgres only)."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            [STORY_ASSIGN_ADVISORY_LOCK_KEY],
        )


def assign_story_thread(article: Article) -> Article:
    """Attach article to a near-dup / open thread / soft peer pair, or leave null.

    Create-once: already-threaded articles are left alone. No singleton threads.
    """
    embedding = _as_list(article.embedding)
    if embedding is None:
        return article
    if article.story_thread_id:
        return article

    with transaction.atomic():
        _acquire_story_assign_lock()
        # Re-read under lock in case another worker just attached a thread.
        article = Article.objects.select_for_update().get(pk=article.pk)
        if article.story_thread_id:
            return article
        embedding = _as_list(article.embedding)
        if embedding is None:
            return article
        return _assign_story_thread_locked(article, embedding)


def _assign_story_thread_locked(article: Article, embedding: list[float]) -> Article:
    published = article.published_at or timezone.now()

    # Lane A: tight same-window near-duplicate.
    window_start = published - DEDUP_WINDOW
    window_end = published + DEDUP_WINDOW
    best_peer: Article | None = None
    best_peer_sim = 0.0
    peers = (
        Article.objects.filter(
            embedding__isnull=False,
            published_at__gte=window_start,
            published_at__lte=window_end,
        )
        .exclude(pk=article.pk)
        .only(
            "id",
            "embedding",
            "story_thread_id",
            "title",
            "published_at",
            "story_label",
        )
    )
    for peer in peers.iterator(chunk_size=200):
        sim = cosine_similarity(embedding, _as_list(peer.embedding))
        if sim > best_peer_sim:
            best_peer_sim = sim
            best_peer = peer

    if best_peer is not None and best_peer_sim >= DEDUP_SIMILARITY:
        return _join_or_create_with_peer(
            article,
            embedding,
            best_peer,
            near_duplicate=True,
            published=published,
        )

    # Lane B: softer match against open thread centroids.
    active_since = published - THREAD_ACTIVE_WINDOW
    best_thread: StoryThread | None = None
    best_thread_sim = 0.0
    for thread in StoryThread.objects.filter(
        centroid__isnull=False,
        last_published_at__gte=active_since,
    ).iterator(chunk_size=100):
        sim = cosine_similarity(embedding, _as_list(thread.centroid))
        if sim > best_thread_sim:
            best_thread_sim = sim
            best_thread = thread

    if best_thread is not None and best_thread_sim >= THREAD_SIMILARITY:
        best_thread.centroid = _ema_centroid(best_thread.centroid, embedding)
        if published >= (best_thread.last_published_at or published):
            best_thread.last_published_at = published
        # Keep existing label stable on join.
        best_thread.save(update_fields=["centroid", "last_published_at", "updated_at"])
        article.near_duplicate_of = None
        article.story_thread = best_thread
        article.save(update_fields=["near_duplicate_of", "story_thread"])
        return article

    # Lane C: soft match against an unthreaded peer → create a shared thread.
    soft_peer: Article | None = None
    soft_sim = 0.0
    unthreaded = (
        Article.objects.filter(
            embedding__isnull=False,
            story_thread__isnull=True,
            published_at__gte=active_since,
            published_at__lte=published + THREAD_ACTIVE_WINDOW,
        )
        .exclude(pk=article.pk)
        .only(
            "id",
            "embedding",
            "story_thread_id",
            "title",
            "published_at",
            "story_label",
        )
    )
    for peer in unthreaded.iterator(chunk_size=200):
        sim = cosine_similarity(embedding, _as_list(peer.embedding))
        if sim > soft_sim:
            soft_sim = sim
            soft_peer = peer

    if soft_peer is not None and soft_sim >= THREAD_SIMILARITY:
        return _join_or_create_with_peer(
            article,
            embedding,
            soft_peer,
            near_duplicate=False,
            published=published,
        )

    # No singleton thread — leave unthreaded.
    article.near_duplicate_of = None
    article.story_thread = None
    article.save(update_fields=["near_duplicate_of", "story_thread"])
    return article


def _join_or_create_with_peer(
    article: Article,
    embedding: list[float],
    peer: Article,
    *,
    near_duplicate: bool,
    published,
) -> Article:
    if near_duplicate:
        article.near_duplicate_of_id = peer.id
    else:
        article.near_duplicate_of = None

    if peer.story_thread_id:
        thread = StoryThread.objects.get(pk=peer.story_thread_id)
        thread.centroid = _ema_centroid(thread.centroid, embedding)
        if published >= (thread.last_published_at or published):
            thread.last_published_at = published
        thread.save(update_fields=["centroid", "last_published_at", "updated_at"])
    else:
        peer_embedding = _as_list(peer.embedding) or embedding
        last_pub = max(peer.published_at or published, published)
        thread = StoryThread.objects.create(
            label=_story_label_for(article, peer),
            centroid=_ema_centroid(peer_embedding, embedding),
            last_published_at=last_pub,
        )
        Article.objects.filter(pk=peer.pk).update(story_thread_id=thread.id)

    article.story_thread = thread
    article.save(update_fields=["near_duplicate_of", "story_thread"])
    return article


def dissolve_singleton_threads() -> tuple[int, int]:
    """Clear sole-member threads and delete empty threads. Returns (articles, threads)."""
    singleton_ids = list(
        StoryThread.objects.annotate(n=Count("articles")).filter(n=1).values_list("id", flat=True)
    )
    articles_cleared = 0
    if singleton_ids:
        articles_cleared = Article.objects.filter(story_thread_id__in=singleton_ids).update(
            story_thread_id=None
        )
        deleted, _ = StoryThread.objects.filter(id__in=singleton_ids).delete()
    else:
        deleted = 0

    empty_ids = list(
        StoryThread.objects.annotate(n=Count("articles")).filter(n=0).values_list("id", flat=True)
    )
    if empty_ids:
        extra, _ = StoryThread.objects.filter(id__in=empty_ids).delete()
        deleted += extra
    return articles_cleared, deleted


def reconcile_story_threads(*, limit: int | None = None) -> dict[str, int]:
    """No-AI repair: dissolve singletons, then assign unthreaded articles with embeddings."""
    cleared, dissolved = dissolve_singleton_threads()
    qs = Article.objects.filter(embedding__isnull=False, story_thread__isnull=True).order_by(
        "published_at", "id"
    )
    if limit is not None:
        qs = qs[:limit]
    assigned = 0
    considered = 0
    for article in qs.iterator(chunk_size=100):
        considered += 1
        before = article.story_thread_id
        assign_story_thread(article)
        article.refresh_from_db(fields=["story_thread_id"])
        if article.story_thread_id and article.story_thread_id != before:
            assigned += 1
    return {
        "singletons_cleared": cleared,
        "threads_deleted": dissolved,
        "unthreaded_considered": considered,
        "newly_threaded": assigned,
    }
