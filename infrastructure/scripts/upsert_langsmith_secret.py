#!/usr/bin/env python3
"""Upsert noise-to-signal/<env>/langsmith from root .env (or LANGSMITH_API_KEY env)."""

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
        "LANGSMITH_SECRET_NAME", f"noise-to-signal/{env_name}/langsmith"
    )
    region = os.environ.get("AWS_REGION", "eu-central-1")
    profile = os.environ.get("AWS_PROFILE", "AdministratorAccess-465836752303")

    dotenv = load_dotenv(root / ".env")
    api_key = os.environ.get("LANGSMITH_API_KEY") or dotenv.get("LANGSMITH_API_KEY")
    if not api_key:
        print("Missing LANGSMITH_API_KEY (root .env or env)", file=sys.stderr)
        return 1

    payload = json.dumps({"LANGSMITH_API_KEY": api_key})

    def aws(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["aws", *args, "--profile", profile, "--region", region],
            check=False,
            capture_output=True,
            text=True,
        )

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
            "noise-to-signal LangSmith API key — manage via just upsert-langsmith",
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
