"""Thin Bedrock AgentCore Memory client for user preferences."""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_NAMESPACE_TEMPLATE = "/preferences/{actorId}"


def actor_id_for_user(user_id: int) -> str:
    return str(user_id)


class PreferenceMemoryClient:
    """Create events, retrieve preference records, and erase by actorId."""

    def __init__(
        self,
        *,
        memory_id: str,
        region: str,
        namespace_template: str = DEFAULT_NAMESPACE_TEMPLATE,
        client: Any | None = None,
    ) -> None:
        self.memory_id = memory_id
        self.region = region
        self.namespace_template = namespace_template
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-agentcore", region_name=self.region)
        return self._client

    def namespace_for(self, actor_id: str) -> str:
        return self.namespace_template.replace("{actorId}", actor_id)

    def record_preference(self, user_id: int, text: str) -> None:
        """Write a short-term event; USER_PREFERENCE strategy extracts LTM."""
        content = (text or "").strip()
        if not content or not self.memory_id:
            return
        actor = actor_id_for_user(user_id)
        session_id = f"prefs-{actor}-{uuid.uuid4().hex[:12]}"
        self.client.create_event(
            memoryId=self.memory_id,
            actorId=actor,
            sessionId=session_id,
            payload=[
                {
                    "conversational": {
                        "role": "USER",
                        "content": {"text": content[:9000]},
                    }
                }
            ],
        )

    def retrieve_preferences(self, user_id: int, *, query: str = "", top_k: int = 10) -> list[str]:
        """Return preference record texts for the actor (best-effort)."""
        if not self.memory_id:
            return []
        actor = actor_id_for_user(user_id)
        namespace = self.namespace_for(actor)
        search_query = (query or "user news reading preferences topics tone sources").strip()
        try:
            response = self.client.retrieve_memory_records(
                memoryId=self.memory_id,
                namespace=namespace,
                searchCriteria={
                    "searchQuery": search_query[:1000],
                    "topK": max(1, min(top_k, 25)),
                },
            )
        except Exception:
            logger.exception("retrieve_memory_records failed for actor=%s", actor)
            return []

        texts: list[str] = []
        for record in response.get("memoryRecordSummaries") or response.get("memoryRecords") or []:
            content = record.get("content") or {}
            text = content.get("text") if isinstance(content, dict) else None
            if not text:
                # Some shapes nest preference JSON under content
                text = record.get("text") or ""
            if isinstance(text, dict):
                text = json.dumps(text, ensure_ascii=False)
            if text:
                texts.append(str(text).strip())
        return [t for t in texts if t]

    def delete_all_for_user(self, user_id: int) -> int:
        """List and delete long-term memory records for actorId (GDPR erase)."""
        if not self.memory_id:
            return 0
        actor = actor_id_for_user(user_id)
        namespace = self.namespace_for(actor)
        deleted = 0
        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "memoryId": self.memory_id,
                "namespace": namespace,
                "maxResults": 100,
            }
            if next_token:
                kwargs["nextToken"] = next_token
            try:
                page = self.client.list_memory_records(**kwargs)
            except Exception:
                logger.exception("list_memory_records failed for actor=%s", actor)
                break
            records = page.get("memoryRecordSummaries") or page.get("memoryRecords") or []
            for record in records:
                record_id = record.get("memoryRecordId") or record.get("recordId")
                if not record_id:
                    continue
                try:
                    self.client.delete_memory_record(
                        memoryId=self.memory_id,
                        memoryRecordId=record_id,
                    )
                    deleted += 1
                except Exception:
                    logger.exception("delete_memory_record failed id=%s", record_id)
            next_token = page.get("nextToken")
            if not next_token:
                break
        return deleted


def get_preference_client() -> PreferenceMemoryClient | None:
    """Build a client from env, or None when AgentCore is not configured."""
    memory_id = (os.environ.get("AGENTCORE_MEMORY_ID") or "").strip()
    if not memory_id:
        return None
    region = (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )
    namespace = (
        os.environ.get("AGENTCORE_PREFERENCE_NAMESPACE") or DEFAULT_NAMESPACE_TEMPLATE
    ).strip()
    return PreferenceMemoryClient(
        memory_id=memory_id,
        region=region,
        namespace_template=namespace,
    )
