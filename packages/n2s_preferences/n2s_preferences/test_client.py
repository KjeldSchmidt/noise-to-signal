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

    def test_record_preference_writes_user_and_assistant_turns(self) -> None:
        api = MagicMock()
        client = PreferenceMemoryClient(
            memory_id="mem-1",
            region="eu-central-1",
            client=api,
        )
        client.record_preference(3, "Less horse-race, more policy analysis")
        api.create_event.assert_called_once()
        kwargs = api.create_event.call_args.kwargs
        self.assertEqual(kwargs["memoryId"], "mem-1")
        self.assertEqual(kwargs["actorId"], "3")
        self.assertTrue(str(kwargs["sessionId"]).startswith("prefs-3-"))
        payload = kwargs["payload"]
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["conversational"]["role"], "USER")
        self.assertEqual(
            payload[0]["conversational"]["content"]["text"],
            "Less horse-race, more policy analysis",
        )
        self.assertEqual(payload[1]["conversational"]["role"], "ASSISTANT")
        self.assertIn("remember", payload[1]["conversational"]["content"]["text"].lower())

    def test_record_preference_noop_when_empty(self) -> None:
        api = MagicMock()
        client = PreferenceMemoryClient(
            memory_id="mem-1",
            region="eu-central-1",
            client=api,
        )
        client.record_preference(3, "  ")
        api.create_event.assert_not_called()

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

    def test_list_preference_records(self) -> None:
        api = MagicMock()
        api.list_memory_records.return_value = {
            "memoryRecordSummaries": [
                {"memoryRecordId": "r1", "content": {"text": "Likes science"}},
                {"memoryRecordId": "r2", "content": {"text": ""}},
            ]
        }
        client = PreferenceMemoryClient(
            memory_id="mem-1",
            region="eu-central-1",
            client=api,
        )
        records = client.list_preference_records(3)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].id, "r1")
        self.assertEqual(records[0].text, "Likes science")
        self.assertEqual(records[1].text, "(empty preference)")

    def test_delete_preference_record(self) -> None:
        api = MagicMock()
        client = PreferenceMemoryClient(
            memory_id="mem-1",
            region="eu-central-1",
            client=api,
        )
        self.assertTrue(client.delete_preference_record(3, "r1"))
        api.delete_memory_record.assert_called_once_with(
            memoryId="mem-1",
            memoryRecordId="r1",
        )

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
