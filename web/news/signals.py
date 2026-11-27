"""Auth/signup side effects for the news app."""

from __future__ import annotations

from typing import Any

from allauth.account.signals import user_signed_up
from django.contrib.auth.models import AbstractBaseUser
from django.dispatch import receiver
from django.http import HttpRequest

from news.services.onboarding import enroll_onboarding


@receiver(user_signed_up)
def enroll_new_user_onboarding(
    request: HttpRequest,
    user: AbstractBaseUser,
    **kwargs: Any,
) -> None:
    """New Google signups start the preference wizard; returning users do not."""
    enroll_onboarding(user)
