"""Unit tests for brief_builder graph (mocked Bedrock / AgentCore / web API)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from n2s_api import (
    BriefBuilderRequest,
    BriefCandidateDTO,
    BriefCompleteResponse,
    BriefUserContextResponse,
)

import build as build_mod
import graph as graph_mod
from schemas import BriefPick, BriefSelection


class BriefGraphTests(unittest.TestCase):
    def test_evaluate_filters_unknown_ids(self) -> None:
        candidates = [
            BriefCandidateDTO(
                article_id=10,
                title="One",
                url="https://example.com/1",
                score=0.8,
            ),
            BriefCandidateDTO(
                article_id=11,
                title="Two",
                url="https://example.com/2",
                score=0.7,
            ),
        ]
        ctx = BriefUserContextResponse(user_id=1, candidates=candidates)
        selection = BriefSelection(
            items=[
                BriefPick(article_id=10, rank=1, score=0.9, reason="Good fit."),
                BriefPick(article_id=999, rank=2, score=0.5, reason="Hallucinated."),
            ]
        )
        model = MagicMock()
        model.with_structured_output.return_value.invoke.return_value = selection
        with patch.object(graph_mod, "get_brief_model", return_value=model):
            out = graph_mod.evaluate(
                {
                    "user_id": 1,
                    "brief_id": 2,
                    "preferences": ["likes climate"],
                    "context": ctx,
                    "candidates": candidates,
                }
            )
        self.assertEqual(len(out["selected"]), 1)
        self.assertEqual(out["selected"][0]["article_id"], 10)

    @patch.object(graph_mod, "complete_brief")
    def test_persist_ready(self, mock_complete: MagicMock) -> None:
        mock_complete.return_value = BriefCompleteResponse(brief_id=5, status="ready", item_count=1)
        graph_mod.persist(
            {
                "user_id": 3,
                "brief_id": 5,
                "selected": [
                    {
                        "article_id": 10,
                        "rank": 1,
                        "score": 0.8,
                        "reason": "Relevant.",
                    }
                ],
            }
        )
        mock_complete.assert_called_once()
        req = mock_complete.call_args[0][0]
        self.assertEqual(req.status, "ready")
        self.assertEqual(len(req.items), 1)


class BriefDispatchTests(unittest.TestCase):
    @patch.object(build_mod, "get_preference_client")
    def test_record_preference(self, mock_get: MagicMock) -> None:
        client = MagicMock()
        mock_get.return_value = client
        out = build_mod.dispatch(
            BriefBuilderRequest(
                action="record_preference",
                user_id=7,
                preference_text="User likes science.",
            )
        )
        self.assertTrue(out["ok"])
        client.record_preference.assert_called_once_with(7, "User likes science.")

    @patch.object(build_mod, "run_build")
    def test_build_dispatch(self, mock_build: MagicMock) -> None:
        out = build_mod.dispatch(BriefBuilderRequest(action="build", user_id=1, brief_id=9))
        self.assertTrue(out["ok"])
        mock_build.assert_called_once()


if __name__ == "__main__":
    unittest.main()
