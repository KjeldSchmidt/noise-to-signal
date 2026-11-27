"""Tests for multilingual story-thread digest DTOs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from n2s_api import StoryThreadMultilangDigest


def test_digest_rejects_empty_labels() -> None:
    with pytest.raises(ValidationError, match="empty label"):
        StoryThreadMultilangDigest.model_validate(
            {
                "localizations": [
                    {"language": "en", "label": "", "summary": "Summary."},
                    {"language": "fr", "label": "Titre", "summary": "Résumé."},
                    {"language": "de", "label": "Titel", "summary": "Zusammenfassung."},
                ]
            }
        )


def test_digest_orders_product_languages() -> None:
    digest = StoryThreadMultilangDigest.model_validate(
        {
            "localizations": [
                {"language": "de", "label": "Titel", "summary": "Zusammenfassung."},
                {"language": "en", "label": "Title", "summary": "Summary."},
                {"language": "fr", "label": "Titre", "summary": "Résumé."},
            ]
        }
    )
    assert [row.language for row in digest.localizations] == ["en", "fr", "de"]
