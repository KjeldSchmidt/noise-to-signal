"""Read/write theme-analysis status + latest report under a fixed S3 prefix."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import boto3

STATUS_KEY = "theme-analysis/status.json"
LATEST_KEY = "theme-analysis/latest.json"


def _bucket() -> str:
    name = (os.environ.get("ANALYSIS_ARTIFACTS_BUCKET") or "").strip()
    if not name:
        raise RuntimeError("ANALYSIS_ARTIFACTS_BUCKET is required")
    return name


def _client() -> Any:
    return boto3.client("s3")


def put_json(key: str, payload: dict[str, Any]) -> None:
    _client().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        ContentType="application/json",
    )


def write_status(
    status: str,
    *,
    started_at: str | None = None,
    finished_at: str | None = None,
    error: str = "",
) -> None:
    put_json(
        STATUS_KEY,
        {
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "error": error,
        },
    )


def write_latest(report: dict[str, Any]) -> None:
    put_json(LATEST_KEY, report)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
