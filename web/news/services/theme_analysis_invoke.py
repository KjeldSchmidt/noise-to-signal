"""Async Event-invoke for the theme_analysis worker."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _lambda_client() -> Any:
    import boto3

    return boto3.client(
        "lambda",
        region_name=getattr(settings, "AWS_REGION", None)
        or getattr(settings, "BEDROCK_REGION", None)
        or None,
    )


def invoke_theme_analysis() -> bool:
    """
    Kick theme_analysis.

    Production: async Lambda Event invoke via THEME_ANALYSIS_FUNCTION_NAME.
    Returns True if invoke was attempted/succeeded; False if unavailable.
    """
    function_name = (getattr(settings, "THEME_ANALYSIS_FUNCTION_NAME", None) or "").strip()
    if not function_name:
        logger.error("THEME_ANALYSIS_FUNCTION_NAME is not configured")
        return False

    _lambda_client().invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=b"{}",
    )
    return True
