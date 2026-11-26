"""Thin Bedrock AgentCore Memory client for user preferences."""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_NAMESPACE_TEMPLATE = "/preferences/{actorId}"


def actor_id_for_user(user_id: int) -> str:
    return str(user_id)


@dataclass(frozen=True)
class PreferenceRecord:
    id: str
    text: str


def _text_from_record(record: dict[str, Any]) -> str:
    content = record.get("content") or {}
    text = content.get("text") if isinstance(content, dict) else None
    if not text:
        text = record.get("text") or ""
    if isinstance(text, dict):
        text = json.dumps(text, ensure_ascii=False)
    return str(text).strip() if text else ""


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
        """Write a short-term event; USER_PREFERENCE strategy extracts LTM.

        AgentCore extracts more reliably from a USER+ASSISTANT turn pair than
        from a lone USER utterance (extraction is still asynchronous).
        """
        content = (text or "").strip()
        if not content or not self.memory_id:
            return
        actor = actor_id_for_user(user_id)
        session_id = f"prefs-{actor}-{uuid.uuid4().hex[:12]}"
        # Cap user text so USER+ASSISTANT stay within a comfortable payload size.
        user_text = content[:8500]
        self.client.create_event(
            memoryId=self.memory_id,
            actorId=actor,
            sessionId=session_id,
            payload=[
                {
                    "conversational": {
                        "role": "USER",
                        "content": {"text": user_text},
                    }
                },
                {
                    "conversational": {
                        "role": "ASSISTANT",
                        "content": {
                            "text": (
                                "Understood. I will remember that reading "
                                "preference when personalizing future briefs."
                            )
                        },
                    }
                },
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
            text = _text_from_record(record)
            if text:
                texts.append(text)
        return texts

    def list_preference_records(self, user_id: int) -> list[PreferenceRecord]:
        """List long-term preference memory records with ids (for Settings UI)."""
        if not self.memory_id:
            return []
        actor = actor_id_for_user(user_id)
        namespace = self.namespace_for(actor)
        out: list[PreferenceRecord] = []
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
                text = _text_from_record(record) or "(empty preference)"
                out.append(PreferenceRecord(id=str(record_id), text=text))
            next_token = page.get("nextToken")
            if not next_token:
                break
        return out

    def delete_preference_record(self, user_id: int, record_id: str) -> bool:
        """Delete one long-term memory record. user_id reserved for actor scoping checks."""
        _ = user_id
        rid = (record_id or "").strip()
        if not self.memory_id or not rid:
            return False
        try:
            self.client.delete_memory_record(
                memoryId=self.memory_id,
                memoryRecordId=rid,
            )
            return True
        except Exception:
            logger.exception("delete_memory_record failed id=%s", rid)
            return False

    def delete_all_for_user(self, user_id: int) -> int:
        """List and delete long-term memory records for actorId (GDPR erase)."""
        deleted = 0
        for record in self.list_preference_records(user_id):
            if self.delete_preference_record(user_id, record.id):
                deleted += 1
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
