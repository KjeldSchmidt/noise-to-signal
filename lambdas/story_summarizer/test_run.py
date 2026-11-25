"""Unit tests for story_summarizer (mocked Bedrock / web API)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from n2s_api import (
    StorySummarizerRequest,
    StoryThreadMemberDTO,
    StoryThreadSummaryContextResponse,
    StoryThreadSummaryUpdateResponse,
)

import main as main_mod
import run as run_mod


class StorySummarizerTests(unittest.TestCase):
    @patch.object(run_mod, "update_story_thread_summary")
    @patch.object(run_mod, "get_story_thread_summary_context")
    @patch.object(run_mod, "get_summary_model")
    def test_run_summary_ok(
        self,
        mock_model: MagicMock,
        mock_context: MagicMock,
        mock_update: MagicMock,
    ) -> None:
        mock_context.return_value = StoryThreadSummaryContextResponse(
            story_thread_id=7,
            label="City Quake",
            articles=[
                StoryThreadMemberDTO(
                    title="Quake hits city",
                    summary="A strong quake struck overnight.",
                    source="Wire",
                    published_at="2026-01-01T00:00:00+00:00",
                )
            ],
        )
        mock_model.return_value.invoke.return_value = MagicMock(
            content="A strong quake struck the city overnight. Rescue crews are responding."
        )
        mock_update.return_value = StoryThreadSummaryUpdateResponse(
            story_thread_id=7,
            summarized_at="2026-01-01T01:00:00+00:00",
            summary_chars=70,
        )
        out = run_mod.run_summary(7)
        self.assertTrue(out["ok"])
        self.assertEqual(out["story_thread_id"], 7)
        mock_update.assert_called_once()

    def test_handler_parses_payload(self) -> None:
        with patch.object(main_mod, "dispatch", return_value={"ok": True}) as mock_dispatch:
            out = main_mod.handler({"story_thread_id": 3})
        self.assertTrue(out["ok"])
        mock_dispatch.assert_called_once()
        req = mock_dispatch.call_args[0][0]
        self.assertIsInstance(req, StorySummarizerRequest)
        self.assertEqual(req.story_thread_id, 3)


if __name__ == "__main__":
    unittest.main()
