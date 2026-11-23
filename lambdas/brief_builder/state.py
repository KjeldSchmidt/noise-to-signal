"""LangGraph state for brief_builder."""

from __future__ import annotations

from typing import NotRequired, TypedDict

from n2s_api import BriefCandidateDTO, BriefUserContextResponse


class BriefState(TypedDict):
    user_id: int
    brief_id: int
    preferences: NotRequired[list[str]]
    context: NotRequired[BriefUserContextResponse | None]
    candidates: NotRequired[list[BriefCandidateDTO]]
    selected: NotRequired[list[dict]]
    error: NotRequired[str]
