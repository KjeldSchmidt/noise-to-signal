"""Placeholder follow-up questions — swap for the LangGraph runner later."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import QuerySet

from news.models import FollowUpAnswer, FollowUpQuestion


def unanswered_questions(user: AbstractBaseUser) -> QuerySet[FollowUpQuestion]:
    answered_ids = FollowUpAnswer.objects.filter(user=user).values_list("question_id", flat=True)
    return FollowUpQuestion.objects.filter(is_active=True).exclude(id__in=answered_ids)


def next_questions(user: AbstractBaseUser, limit: int = 3) -> list[FollowUpQuestion]:
    return list(unanswered_questions(user)[:limit])
