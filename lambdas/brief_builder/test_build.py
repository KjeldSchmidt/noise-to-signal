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
                kind="article",
                article_id=10,
                title="One",
                url="https://example.com/1",
                score=0.8,
            ),
            BriefCandidateDTO(
                kind="thread",
                article_id=20,
                story_thread_id=5,
                title="Two thread",
                url="https://example.com/2",
                score=0.7,
                article_count=3,
            ),
        ]
        ctx = BriefUserContextResponse(user_id=1, candidates=candidates)
        selection = BriefSelection(
            items=[
                BriefPick(candidate_id="article:10", rank=1, score=0.9, reason="Good fit."),
                BriefPick(candidate_id="thread:999", rank=2, score=0.5, reason="Hallucinated."),
                BriefPick(candidate_id="thread:5", rank=3, score=0.8, reason="Developing story."),
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
        self.assertEqual(len(out["selected"]), 2)
        self.assertEqual(out["selected"][0]["kind"], "article")
        self.assertEqual(out["selected"][0]["article_id"], 10)
        self.assertEqual(out["selected"][1]["kind"], "thread")
        self.assertEqual(out["selected"][1]["story_thread_id"], 5)

    @patch.object(graph_mod, "complete_brief")
    def test_persist_ready(self, mock_complete: MagicMock) -> None:
        mock_complete.return_value = BriefCompleteResponse(brief_id=5, status="ready", item_count=1)
        graph_mod.persist(
            {
                "user_id": 3,
                "brief_id": 5,
                "selected": [
                    {
                        "kind": "article",
                        "article_id": 10,
                        "story_thread_id": None,
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
        self.assertEqual(req.items[0].kind, "article")

    @patch.object(graph_mod, "complete_brief")
    def test_persist_thread(self, mock_complete: MagicMock) -> None:
        mock_complete.return_value = BriefCompleteResponse(brief_id=5, status="ready", item_count=1)
        graph_mod.persist(
            {
                "user_id": 3,
                "brief_id": 5,
                "selected": [
                    {
                        "kind": "thread",
                        "article_id": None,
                        "story_thread_id": 9,
                        "rank": 1,
                        "score": 0.85,
                        "reason": "Major developing story.",
                    }
                ],
            }
        )
        req = mock_complete.call_args[0][0]
        self.assertEqual(req.items[0].kind, "thread")
        self.assertEqual(req.items[0].story_thread_id, 9)


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

    @patch.object(build_mod, "get_preference_client")
    def test_list_preferences(self, mock_get: MagicMock) -> None:
        from n2s_preferences import PreferenceRecord

        client = MagicMock()
        client.list_preference_records.return_value = [
            PreferenceRecord(id="r1", text="Likes climate"),
        ]
        mock_get.return_value = client
        out = build_mod.dispatch(BriefBuilderRequest(action="list_preferences", user_id=7))
        self.assertTrue(out["ok"])
        self.assertEqual(out["memories"], [{"id": "r1", "text": "Likes climate"}])

    @patch.object(build_mod, "get_preference_client")
    def test_delete_preference(self, mock_get: MagicMock) -> None:
        client = MagicMock()
        client.delete_preference_record.return_value = True
        mock_get.return_value = client
        out = build_mod.dispatch(
            BriefBuilderRequest(
                action="delete_preference",
                user_id=7,
                memory_record_id="r1",
            )
        )
        self.assertTrue(out["ok"])
        client.delete_preference_record.assert_called_once_with(7, "r1")

    @patch.object(build_mod, "run_build")
    def test_build_dispatch(self, mock_build: MagicMock) -> None:
        out = build_mod.dispatch(BriefBuilderRequest(action="build", user_id=1, brief_id=9))
        self.assertTrue(out["ok"])
        mock_build.assert_called_once()


class PersonalizationScoreTests(unittest.TestCase):
    def test_theme_boosts_and_sorts(self) -> None:
        from prompts import apply_personalization_scores

        cands = [
            BriefCandidateDTO(
                article_id=1,
                title="Sports",
                url="https://example.com/s",
                themes=["sports"],
                score=0.5,
            ),
            BriefCandidateDTO(
                article_id=2,
                title="Climate",
                url="https://example.com/c",
                themes=["environment"],
                score=0.5,
            ),
        ]
        out = apply_personalization_scores(
            cands,
            [("environment", 2.0), ("sports", -1.0)],
            [],
        )
        self.assertEqual(out[0].article_id, 2)
        self.assertGreater(out[0].score, out[1].score)
        self.assertLess(out[1].score, 0.5)

    def test_neutral_is_identity(self) -> None:
        from prompts import apply_personalization_scores

        cands = [
            BriefCandidateDTO(
                article_id=1,
                title="A",
                url="https://example.com/a",
                score=1.2,
            ),
            BriefCandidateDTO(
                article_id=2,
                title="B",
                url="https://example.com/b",
                score=0.8,
            ),
        ]
        out = apply_personalization_scores(cands, [], [])
        self.assertEqual([c.article_id for c in out], [1, 2])
        self.assertAlmostEqual(out[0].score, 1.2, places=4)
        self.assertAlmostEqual(out[1].score, 0.8, places=4)

    def test_place_match_raises_local(self) -> None:
        from n2s_api import BriefLocationDTO

        from prompts import PLACE_MATCH_BETA, apply_personalization_scores

        cands = [
            BriefCandidateDTO(
                article_id=1,
                title="Remote",
                url="https://example.com/r",
                country_code="us",
                geo_level="country",
                score=1.0,
            ),
            BriefCandidateDTO(
                article_id=2,
                title="Cologne",
                url="https://example.com/c",
                country_code="de",
                geo_level="locality",
                admin1="North Rhine-Westphalia",
                locality="Cologne",
                latitude=50.94,
                longitude=6.96,
                score=1.0,
            ),
        ]
        locations = [
            BriefLocationDTO(
                label="Cologne",
                country_code="de",
                geo_level="locality",
                admin1="North Rhine-Westphalia",
                locality="Cologne",
                latitude=50.94,
                longitude=6.96,
            )
        ]
        out = apply_personalization_scores(cands, [], locations)
        self.assertEqual(out[0].article_id, 2)
        self.assertAlmostEqual(out[0].score, 1.0 * (1.0 + PLACE_MATCH_BETA * 1.0), places=4)
        self.assertAlmostEqual(out[1].score, 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
