"""Resolve and persist multilingual story-thread display copy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from django.utils import timezone
from n2s_api import PRODUCT_THREAD_LANGUAGES, StoryThreadLocalizationDTO

from news.models import StoryThread, StoryThreadLocalization


@dataclass(frozen=True)
class ThreadCopy:
    label: str
    summary: str
    language: str = ""


def _localization_map(thread: StoryThread) -> dict[str, StoryThreadLocalization]:
    rows = list(StoryThreadLocalization.objects.filter(story_thread=thread))
    return {row.language.code: row for row in rows}


def resolve_thread_copy(
    thread: StoryThread,
    preferred: Sequence[str],
    *,
    fallback_title: str = "",
) -> ThreadCopy:
    """
    Pick label+summary for display.

    Order: preferred languages → en → any localization → English mirrors → fallback title.
    """
    by_lang = _localization_map(thread)
    candidates: list[str] = []
    for code in preferred:
        code_norm = (code or "").strip().lower()
        if code_norm and code_norm not in candidates:
            candidates.append(code_norm)
    if "en" not in candidates:
        candidates.append("en")
    for code in by_lang:
        if code not in candidates:
            candidates.append(code)

    for code in candidates:
        row = by_lang.get(code)
        if row is None:
            continue
        label = (row.label or "").strip()
        summary = (row.summary or "").strip()
        if label or summary:
            return ThreadCopy(
                label=label or (thread.label or "").strip() or fallback_title,
                summary=summary or (thread.summary or "").strip(),
                language=code,
            )

    mirror_label = (thread.label or "").strip()
    mirror_summary = (thread.summary or "").strip()
    if mirror_label or mirror_summary:
        return ThreadCopy(
            label=mirror_label or fallback_title,
            summary=mirror_summary,
            language="en" if mirror_label or mirror_summary else "",
        )
    return ThreadCopy(label=fallback_title, summary="", language="")


def apply_thread_display_copy(
    thread: StoryThread,
    preferred: Sequence[str],
    *,
    fallback_title: str = "",
) -> StoryThread:
    """Attach non-persisted display_label / display_summary for templates."""
    copy = resolve_thread_copy(thread, preferred, fallback_title=fallback_title)
    display = cast(Any, thread)
    display.display_label = copy.label
    display.display_summary = copy.summary
    display.display_language = copy.language
    return thread


def upsert_thread_localizations(
    thread: StoryThread,
    localizations: Sequence[StoryThreadLocalizationDTO] | Sequence[Mapping[str, str]],
) -> tuple[StoryThread, int]:
    """
    Upsert localization rows and mirror English onto StoryThread.label/summary.

    Returns (thread, localization_count_written).
    """
    rows: list[StoryThreadLocalizationDTO] = []
    for item in localizations:
        if isinstance(item, StoryThreadLocalizationDTO):
            rows.append(item)
        else:
            rows.append(StoryThreadLocalizationDTO.model_validate(item))

    written = 0
    en_label = ""
    en_summary = ""
    for row in rows:
        language = row.language
        label = (row.label or "").strip()[:300]
        summary = (row.summary or "").strip()[:8000]
        StoryThreadLocalization.objects.update_or_create(
            story_thread=thread,
            language_id=language,
            defaults={"label": label, "summary": summary},
        )
        written += 1
        if language == "en":
            en_label = label
            en_summary = summary

    now = timezone.now()
    if en_label or en_summary:
        thread.label = en_label[:300]
        thread.summary = en_summary
        thread.summarized_at = now
        thread.save(update_fields=["label", "summary", "summarized_at", "updated_at"])
    else:
        thread.summarized_at = now
        thread.save(update_fields=["summarized_at", "updated_at"])
    return thread, written


def product_localizations_complete(thread: StoryThread) -> bool:
    """True when en/fr/de localization rows all exist with some text."""
    by_lang = _localization_map(thread)
    for code in PRODUCT_THREAD_LANGUAGES:
        row = by_lang.get(code)
        if row is None:
            return False
        if not (row.label or "").strip() and not (row.summary or "").strip():
            return False
    return True


def localization_count(thread: StoryThread) -> int:
    return StoryThreadLocalization.objects.filter(story_thread=thread).count()
