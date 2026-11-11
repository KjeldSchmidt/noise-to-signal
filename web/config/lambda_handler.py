"""AWS Lambda entrypoint: Mangum (HTTP) + optional manage-command invoke."""

from __future__ import annotations

import json
import os
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from mangum import Mangum  # noqa: E402

from config.asgi import application  # noqa: E402  # sets up Django (Mangum needs ASGI)

_mangum = Mangum(application, lifespan="off")


def handler(event: dict[str, Any], context: Any) -> Any:
    """Route Function URL events to Django, or run manage commands.

    CI invoke payload example::

        {"manage": ["migrate", "--noinput"]}
    """
    if isinstance(event, dict) and "manage" in event:
        from django.core.management import call_command

        args = event["manage"]
        if not isinstance(args, list) or not args:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "manage must be a non-empty list"}),
            }
        call_command(*args)
        return {"ok": True, "manage": args}

    return _mangum(event, context)
