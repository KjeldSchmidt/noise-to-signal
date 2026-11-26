#!/usr/bin/env python3
"""Upsert noise-to-signal/<env>/google-oauth from web/.env (or GOOGLE_* env vars)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    env_name = os.environ.get("APP_ENV", "dev")
    secret_name = os.environ.get(
        "GOOGLE_OAUTH_SECRET_NAME", f"noise-to-signal/{env_name}/google-oauth"
    )
    region = os.environ.get("AWS_REGION", "eu-central-1")
    profile = (os.environ.get("AWS_PROFILE") or "").strip()

    dotenv = load_dotenv(root / "web" / ".env")
    client_id = (
        os.environ.get("GOOGLE_CLIENT_ID")
        or dotenv.get("GOOGLE_CLIENT_ID")
        or dotenv.get("CLIENT_ID")
    )
    client_secret = (
        os.environ.get("GOOGLE_CLIENT_SECRET")
        or dotenv.get("GOOGLE_CLIENT_SECRET")
        or dotenv.get("CLIENT_SECRET")
    )
    if not client_id or not client_secret:
        print("Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (web/.env)", file=sys.stderr)
        return 1

    payload = json.dumps(
        {
            "GOOGLE_CLIENT_ID": client_id,
            "GOOGLE_CLIENT_SECRET": client_secret,
        }
    )

    def aws(*args: str) -> subprocess.CompletedProcess[str]:
        cmd = ["aws", *args, "--region", region]
        if profile:
            cmd.extend(["--profile", profile])
        return subprocess.run(cmd, check=False, capture_output=True, text=True)

    exists = aws("secretsmanager", "describe-secret", "--secret-id", secret_name)
    if exists.returncode == 0:
        put = aws(
            "secretsmanager",
            "put-secret-value",
            "--secret-id",
            secret_name,
            "--secret-string",
            payload,
        )
        if put.returncode != 0:
            print(put.stderr, file=sys.stderr)
            return put.returncode
        print(f"Updated {secret_name}")
    else:
        create = aws(
            "secretsmanager",
            "create-secret",
            "--name",
            secret_name,
            "--description",
            "noise-to-signal Google OAuth — manage in AWS Console",
            "--secret-string",
            payload,
        )
        if create.returncode != 0:
            print(create.stderr, file=sys.stderr)
            return create.returncode
        print(f"Created {secret_name}")

    desc = aws(
        "secretsmanager",
        "describe-secret",
        "--secret-id",
        secret_name,
        "--query",
        "ARN",
        "--output",
        "text",
    )
    print(desc.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
