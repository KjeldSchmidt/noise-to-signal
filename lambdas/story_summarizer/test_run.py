"""Unit tests for story_summarizer (mocked Bedrock / web API)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from n2s_api import (
    StorySummarizerRequest,
    StoryThreadLocalizationDTO,
    StoryThreadMemberDTO,
    StoryThreadMultilangDigest,
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
                    language="en",
                )
            ],
        )
        digest = StoryThreadMultilangDigest(
            localizations=[
                StoryThreadLocalizationDTO(
                    language="en",
                    label="City Quake",
                    summary=(
                        "A strong quake struck the city overnight. Rescue crews are responding."
                    ),
                ),
                StoryThreadLocalizationDTO(
                    language="fr",
                    label="Séisme urbain",
                    summary=(
                        "Un fort séisme a frappé la ville cette nuit. Les secours interviennent."
                    ),
                ),
                StoryThreadLocalizationDTO(
                    language="de",
                    label="Stadtbeben",
                    summary=(
                        "Ein starkes Beben traf die Stadt über Nacht. "
                        "Rettungskräfte sind im Einsatz."
                    ),
                ),
            ]
        )
        structured = MagicMock()
        structured.invoke.return_value = digest
        mock_model.return_value.with_structured_output.return_value = structured
        mock_update.return_value = StoryThreadSummaryUpdateResponse(
            story_thread_id=7,
            summarized_at="2026-01-01T01:00:00+00:00",
            summary_chars=70,
            localization_count=3,
        )
        out = run_mod.run_summary(7)
        self.assertTrue(out["ok"])
        self.assertEqual(out["story_thread_id"], 7)
        self.assertEqual(out["localization_count"], 3)
        mock_update.assert_called_once()
        req = mock_update.call_args[0][0]
        self.assertEqual(len(req.localizations), 3)
        self.assertEqual(req.localizations[0].language, "en")

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
