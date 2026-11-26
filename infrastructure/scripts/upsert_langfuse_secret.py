#!/usr/bin/env python3
"""Upsert noise-to-signal/<env>/langfuse from root .env (or LANGFUSE_* env)."""

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
        "LANGFUSE_SECRET_NAME", f"noise-to-signal/{env_name}/langfuse"
    )
    region = os.environ.get("AWS_REGION", "eu-central-1")
    profile = (os.environ.get("AWS_PROFILE") or "").strip()

    dotenv = load_dotenv(root / ".env")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY") or dotenv.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY") or dotenv.get("LANGFUSE_SECRET_KEY")
    base_url = (
        os.environ.get("LANGFUSE_BASE_URL")
        or dotenv.get("LANGFUSE_BASE_URL")
        or "https://cloud.langfuse.com"
    )
    if not public_key or not secret_key:
        print(
            "Missing LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY (root .env or env)",
            file=sys.stderr,
        )
        return 1

    payload = json.dumps(
        {
            "LANGFUSE_PUBLIC_KEY": public_key,
            "LANGFUSE_SECRET_KEY": secret_key,
            "LANGFUSE_BASE_URL": base_url,
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
            "noise-to-signal Langfuse keys — manage via just upsert-langfuse",
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
