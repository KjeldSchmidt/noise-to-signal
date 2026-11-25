"""Pure theme–embedding alignment metrics + UMAP (no I/O)."""

from __future__ import annotations

import os
import tempfile
from typing import Any

import numpy as np
from n2s_api import ArticleEmbeddingExportRow, ThemeDTO, decode_embedding_f32_b64

UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.1
NEIGHBORHOOD_K = 10
MIN_THEME_COUNT = 2


def _ensure_numba_cache_dir() -> None:
    """Point Numba at a writable cache (Lambda site-packages are read-only)."""
    if os.environ.get("NUMBA_CACHE_DIR"):
        return
    cache_dir = os.path.join(tempfile.gettempdir(), "numba_cache")
    os.makedirs(cache_dir, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = cache_dir


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return matrix / norms


def _cosine_matrix(normalized: np.ndarray) -> np.ndarray:
    return normalized @ normalized.T


def rows_to_matrix(
    rows: list[ArticleEmbeddingExportRow],
) -> tuple[np.ndarray, list[ArticleEmbeddingExportRow]]:
    """Decode rows with ≥1 theme; skip malformed vectors."""
    kept: list[ArticleEmbeddingExportRow] = []
    vectors: list[list[float]] = []
    for row in rows:
        if not row.theme_slugs:
            continue
        try:
            vec = decode_embedding_f32_b64(row.embedding_b64)
        except ValueError:
            continue
        kept.append(row)
        vectors.append(vec)
    if not vectors:
        return np.zeros((0, 1024), dtype=np.float64), []
    return np.asarray(vectors, dtype=np.float64), kept


def compute_report(
    rows: list[ArticleEmbeddingExportRow],
    themes: list[ThemeDTO],
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Build the latest.json payload from export rows + theme catalog."""
    matrix, kept = rows_to_matrix(rows)
    catalog = [(t.slug, t.label) for t in themes]
    slug_to_label = {slug: label for slug, label in catalog}

    if matrix.shape[0] == 0:
        return {
            "generated_at": generated_at,
            "article_count": 0,
            "themes": [],
            "centroid_similarity": {"themes": [], "matrix": []},
            "neighborhood_purity_k10": None,
            "umap": {"points": []},
        }

    normalized = _l2_normalize(matrix)
    theme_indices: dict[str, list[int]] = {}
    for i, row in enumerate(kept):
        for slug in row.theme_slugs:
            theme_indices.setdefault(slug, []).append(i)

    # Prefer catalog order; append any unexpected slugs at the end.
    ordered_slugs = [slug for slug, _ in catalog if slug in theme_indices]
    for slug in sorted(theme_indices):
        if slug not in ordered_slugs:
            ordered_slugs.append(slug)

    centroids: dict[str, np.ndarray] = {}
    for slug in ordered_slugs:
        idxs = theme_indices[slug]
        centroids[slug] = _l2_normalize(normalized[idxs].mean(axis=0, keepdims=True))[0]

    theme_stats: list[dict[str, Any]] = []
    for slug in ordered_slugs:
        idxs = theme_indices[slug]
        count = len(idxs)
        centroid = centroids[slug]
        within = float(np.mean(normalized[idxs] @ centroid)) if count else 0.0
        other_centroids = [centroids[s] for s in ordered_slugs if s != slug]
        if other_centroids:
            between = float(np.mean(centroid @ np.stack(other_centroids, axis=1)))
        else:
            between = 0.0
        theme_stats.append(
            {
                "slug": slug,
                "label": slug_to_label.get(slug, slug),
                "count": count,
                "within_mean": round(within, 6),
                "between_mean": round(between, 6),
            }
        )

    heat_slugs = [s for s in ordered_slugs if len(theme_indices[s]) >= MIN_THEME_COUNT]
    heat_matrix: list[list[float]] = []
    for a in heat_slugs:
        row_vals: list[float] = []
        for b in heat_slugs:
            row_vals.append(round(float(centroids[a] @ centroids[b]), 6))
        heat_matrix.append(row_vals)

    purity = _neighborhood_purity(normalized, kept, k=NEIGHBORHOOD_K)
    umap_points = _umap_points(normalized, kept)

    return {
        "generated_at": generated_at,
        "article_count": len(kept),
        "themes": theme_stats,
        "centroid_similarity": {"themes": heat_slugs, "matrix": heat_matrix},
        "neighborhood_purity_k10": round(purity, 6) if purity is not None else None,
        "umap": {"points": umap_points},
    }


def _neighborhood_purity(
    normalized: np.ndarray,
    kept: list[ArticleEmbeddingExportRow],
    *,
    k: int,
) -> float | None:
    n = normalized.shape[0]
    if n < 2:
        return None
    kk = min(k, n - 1)
    sims = _cosine_matrix(normalized)
    np.fill_diagonal(sims, -np.inf)
    theme_sets = [set(row.theme_slugs) for row in kept]
    scores: list[float] = []
    for i in range(n):
        neighbor_idx = np.argpartition(-sims[i], kk)[:kk]
        hits = sum(1 for j in neighbor_idx if theme_sets[i] & theme_sets[int(j)])
        scores.append(hits / kk)
    return float(np.mean(scores))


def _umap_points(
    normalized: np.ndarray,
    kept: list[ArticleEmbeddingExportRow],
) -> list[dict[str, Any]]:
    n = normalized.shape[0]
    if n < 3:
        return []
    n_neighbors = min(UMAP_N_NEIGHBORS, n - 1)
    _ensure_numba_cache_dir()
    try:
        import umap  # noqa: PLC0415 — heavy optional import at compute time
    except ImportError:
        return []

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=UMAP_MIN_DIST,
        metric="cosine",
        random_state=42,
        compatibility_layout=True,
    )
    coords = reducer.fit_transform(normalized)
    points: list[dict[str, Any]] = []
    for i, row in enumerate(kept):
        primary = row.theme_slugs[0] if row.theme_slugs else ""
        points.append(
            {
                "id": row.id,
                "title": row.title,
                "themes": list(row.theme_slugs),
                "primary_theme": primary,
                "x": round(float(coords[i, 0]), 5),
                "y": round(float(coords[i, 1]), 5),
            }
        )
    return points
