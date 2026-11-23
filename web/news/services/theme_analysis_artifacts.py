"""S3 get/put for theme-analysis status + latest report."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from django.conf import settings

STATUS_KEY = "theme-analysis/status.json"
LATEST_KEY = "theme-analysis/latest.json"

logger = logging.getLogger(__name__)


def _bucket() -> str:
    return (getattr(settings, "ANALYSIS_ARTIFACTS_BUCKET", None) or "").strip()


def _client() -> Any:
    import boto3

    return boto3.client(
        "s3",
        region_name=getattr(settings, "AWS_REGION", None) or None,
    )


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def put_json(key: str, payload: dict[str, Any]) -> None:
    bucket = _bucket()
    if not bucket:
        raise RuntimeError("ANALYSIS_ARTIFACTS_BUCKET is not configured")
    _client().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        ContentType="application/json",
    )


def get_json(key: str) -> dict[str, Any] | None:
    from botocore.exceptions import ClientError

    bucket = _bucket()
    if not bucket:
        return None
    try:
        response = _client().get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        data = json.loads(body.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "404", "NoSuchBucket", "AccessDenied"}:
            return None
        logger.warning("get_json %s failed: %s", key, exc)
        return None
    except Exception as exc:
        logger.warning("get_json %s failed: %s", key, exc)
        return None


def load_status() -> dict[str, Any] | None:
    return get_json(STATUS_KEY)


def load_latest() -> dict[str, Any] | None:
    return get_json(LATEST_KEY)


def mark_running() -> None:
    put_json(
        STATUS_KEY,
        {
            "status": "running",
            "started_at": utc_now_iso(),
            "finished_at": None,
            "error": "",
        },
    )
