"""Near-duplicate detection and story-thread assignment from article embeddings."""

from __future__ import annotations

import math
from datetime import timedelta

from django.utils import timezone

from news.models import Article, StoryThread

# Cosine similarity thresholds (Cohere vectors are typically L2-normalized).
DEDUP_SIMILARITY = 0.92
THREAD_SIMILARITY = 0.78
DEDUP_WINDOW = timedelta(hours=48)
THREAD_ACTIVE_WINDOW = timedelta(days=45)
CENTROID_EMA_ALPHA = 0.35


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


def assign_story_thread(article: Article) -> Article:
    """Attach article to a near-dup peer and/or story thread; update centroid.

    Safe to call repeatedly; no-ops when the article has no embedding.
    """
    embedding = _as_list(article.embedding)
    if embedding is None:
        return article

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
        .only("id", "embedding", "story_thread_id", "title", "published_at")
    )
    for peer in peers.iterator(chunk_size=200):
        sim = cosine_similarity(embedding, _as_list(peer.embedding))
        if sim > best_peer_sim:
            best_peer_sim = sim
            best_peer = peer

    if best_peer is not None and best_peer_sim >= DEDUP_SIMILARITY:
        article.near_duplicate_of_id = best_peer.id
        if best_peer.story_thread_id:
            thread = StoryThread.objects.get(pk=best_peer.story_thread_id)
        else:
            thread = StoryThread.objects.create(
                label=(best_peer.title or article.title)[:300],
                centroid=_as_list(best_peer.embedding) or embedding,
                last_published_at=max(
                    best_peer.published_at or published,
                    published,
                ),
            )
            Article.objects.filter(pk=best_peer.pk).update(story_thread_id=thread.id)
        thread.centroid = _ema_centroid(thread.centroid, embedding)
        if published >= (thread.last_published_at or published):
            thread.last_published_at = published
            if article.title and not thread.label:
                thread.label = article.title[:300]
        thread.save(update_fields=["centroid", "last_published_at", "label", "updated_at"])
        article.story_thread = thread
        article.save(
            update_fields=["near_duplicate_of", "story_thread"]
        )
        return article

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
        best_thread.save(update_fields=["centroid", "last_published_at", "updated_at"])
        article.near_duplicate_of = None
        article.story_thread = best_thread
        article.save(update_fields=["near_duplicate_of", "story_thread"])
        return article

    # New event thread.
    thread = StoryThread.objects.create(
        label=(article.title or "")[:300],
        centroid=embedding,
        last_published_at=published,
    )
    article.near_duplicate_of = None
    article.story_thread = thread
    article.save(update_fields=["near_duplicate_of", "story_thread"])
    return article
