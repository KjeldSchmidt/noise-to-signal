"""Unit tests for preference client helpers (no AWS)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from n2s_preferences.client import PreferenceMemoryClient, actor_id_for_user


class PreferenceClientTests(unittest.TestCase):
    def test_actor_id(self) -> None:
        self.assertEqual(actor_id_for_user(42), "42")

    def test_namespace(self) -> None:
        client = PreferenceMemoryClient(
            memory_id="mem-1",
            region="eu-central-1",
            namespace_template="/preferences/{actorId}",
            client=MagicMock(),
        )
        self.assertEqual(client.namespace_for("9"), "/preferences/9")

    def test_retrieve_parses_summaries(self) -> None:
        api = MagicMock()
        api.retrieve_memory_records.return_value = {
            "memoryRecordSummaries": [
                {"content": {"text": "Prefers climate coverage"}},
                {"content": {"text": ""}},
            ]
        }
        client = PreferenceMemoryClient(
            memory_id="mem-1",
            region="eu-central-1",
            client=api,
        )
        texts = client.retrieve_preferences(3)
        self.assertEqual(texts, ["Prefers climate coverage"])

    def test_delete_all(self) -> None:
        api = MagicMock()
        api.list_memory_records.return_value = {
            "memoryRecordSummaries": [
                {"memoryRecordId": "r1"},
                {"memoryRecordId": "r2"},
            ]
        }
        client = PreferenceMemoryClient(
            memory_id="mem-1",
            region="eu-central-1",
            client=api,
        )
        deleted = client.delete_all_for_user(3)
        self.assertEqual(deleted, 2)
        self.assertEqual(api.delete_memory_record.call_count, 2)


if __name__ == "__main__":
    unittest.main()
