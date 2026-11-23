"""Erase AgentCore preference records for a user (GDPR / privacy email flow)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from n2s_api import BriefBuilderRequest

from news.services.brief_invoke import invoke_brief_builder

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Enqueue erase of Bedrock AgentCore preference memory for a user "
        "(via brief_builder worker)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--user-id", type=int, default=None)
        parser.add_argument("--email", type=str, default="")

    def handle(self, *args, **options) -> None:
        user_id: int | None = options.get("user_id")
        email = (options.get("email") or "").strip()
        if user_id is None and not email:
            raise CommandError("Provide --user-id or --email")
        if email:
            try:
                user = User.objects.get(email__iexact=email)
            except User.DoesNotExist as exc:
                raise CommandError(f"No user with email {email}") from exc
            user_id = int(user.pk)
        assert user_id is not None

        invoke_brief_builder(BriefBuilderRequest(action="erase_preferences", user_id=user_id))
        self.stdout.write(
            self.style.SUCCESS(
                f"Enqueued preference erase for user {user_id} "
                "(processed by brief_builder / AgentCore)."
            )
        )
