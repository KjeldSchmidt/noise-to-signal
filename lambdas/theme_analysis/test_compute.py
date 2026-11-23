"""Unit tests for theme–embedding metrics (no S3 / HTTP)."""

from __future__ import annotations

import math

import numpy as np
from n2s_api import ArticleEmbeddingExportRow, ThemeDTO, encode_embedding_f32_b64

from compute import compute_report, rows_to_matrix


def _unit(dim0: float, dim1: float = 0.0) -> list[float]:
    vec = [0.0] * 1024
    vec[0] = dim0
    vec[1] = dim1
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _row(article_id: int, themes: list[str], vec: list[float]) -> ArticleEmbeddingExportRow:
    return ArticleEmbeddingExportRow(
        id=article_id,
        title=f"Article {article_id}",
        theme_slugs=themes,
        embedding_b64=encode_embedding_f32_b64(vec),
    )


def test_rows_to_matrix_skips_unthemed() -> None:
    rows = [
        _row(1, ["tech"], _unit(1.0)),
        _row(2, [], _unit(0.0, 1.0)),
    ]
    matrix, kept = rows_to_matrix(rows)
    assert matrix.shape == (1, 1024)
    assert [r.id for r in kept] == [1]


def test_compute_report_centroids_and_cohesion() -> None:
    # Two tight theme clusters nearly orthogonal.
    rows = [
        _row(1, ["tech"], _unit(1.0, 0.05)),
        _row(2, ["tech"], _unit(1.0, -0.05)),
        _row(3, ["sports"], _unit(0.05, 1.0)),
        _row(4, ["sports"], _unit(-0.05, 1.0)),
    ]
    themes = [
        ThemeDTO(slug="tech", label="Tech"),
        ThemeDTO(slug="sports", label="Sports"),
    ]
    report = compute_report(rows, themes, generated_at="2026-01-01T00:00:00Z")
    assert report["article_count"] == 4
    by_slug = {t["slug"]: t for t in report["themes"]}
    assert by_slug["tech"]["count"] == 2
    assert by_slug["sports"]["count"] == 2
    assert by_slug["tech"]["within_mean"] > by_slug["tech"]["between_mean"]
    assert by_slug["sports"]["within_mean"] > by_slug["sports"]["between_mean"]
    heat = report["centroid_similarity"]
    assert heat["themes"] == ["tech", "sports"]
    assert heat["matrix"][0][0] == 1.0
    assert heat["matrix"][1][1] == 1.0
    assert heat["matrix"][0][1] < 0.5
    assert report["neighborhood_purity_k10"] is not None
    # With only 4 points, k collapses to 3 so purity can be <0.5; just ensure computed.
    assert 0.0 <= report["neighborhood_purity_k10"] <= 1.0


def test_umap_smoke_small_set() -> None:
    rng = np.random.default_rng(0)
    rows: list[ArticleEmbeddingExportRow] = []
    for i in range(30):
        base = rng.normal(size=1024).astype(np.float64)
        theme = "tech" if i < 15 else "sports"
        # Nudge clusters apart on first dims.
        if theme == "tech":
            base[0] += 3.0
        else:
            base[1] += 3.0
        norm = float(np.linalg.norm(base)) or 1.0
        vec = (base / norm).tolist()
        rows.append(_row(i + 1, [theme], vec))
    themes = [
        ThemeDTO(slug="tech", label="Tech"),
        ThemeDTO(slug="sports", label="Sports"),
    ]
    report = compute_report(rows, themes, generated_at="2026-01-01T00:00:00Z")
    points = report["umap"]["points"]
    assert len(points) == 30
    assert all("x" in p and "y" in p and p["primary_theme"] for p in points)
