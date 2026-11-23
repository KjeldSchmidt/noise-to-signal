"""Unit tests for news_chat LangGraph pipeline (mocked models / tools)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, ToolMessage
from n2s_api import ChatCitation, ChatHistoryMessage, ChatWorkerRequest, ContextChunk

import graph as graph_mod
import prompts
from schemas import AnswerPayload, ScopeDecision


class PromptsTests(unittest.TestCase):
    def test_format_chunk_includes_article_id(self) -> None:
        chunk = ContextChunk(
            article_id=1,
            title="Floods",
            source="NPR",
            summary="Water rising.",
        )
        text = prompts.format_chunk(chunk)
        self.assertIn("<<<DATA>>>", text)
        self.assertIn("article_id: 1", text)
        self.assertIn("Floods", text)

    def test_empty_list_intro_helper(self) -> None:
        self.assertTrue(graph_mod._reply_looks_like_empty_list_intro("Here are the articles:"))
        self.assertFalse(
            graph_mod._reply_looks_like_empty_list_intro("Here are the articles:\n- One")
        )


class ChatPipelineTests(unittest.TestCase):
    def _request(self, message: str = "What happened?") -> ChatWorkerRequest:
        return ChatWorkerRequest(
            scope="brief",
            user_id=42,
            message=message,
            history=[ChatHistoryMessage(role="user", content="Earlier Q")],
            chunks=[
                ContextChunk(
                    article_id=9,
                    title="Summit ends",
                    source="BBC",
                    place_label="Geneva",
                    story_label="Climate summit",
                    summary="Leaders agreed on a draft.",
                    url="https://example.com/summit",
                )
            ],
        )

    @patch("graph.get_classifier_model")
    def test_refuse_off_topic(self, mock_get_classifier: MagicMock) -> None:
        structured = MagicMock()
        structured.invoke.return_value = ScopeDecision(allowed=False, reason="off_topic")
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        from chat import run_chat

        with patch("graph.get_answer_model") as mock_answer:
            out = run_chat(self._request("Write me a poem"))
            mock_answer.assert_not_called()

        self.assertTrue(out.refused)
        self.assertEqual(out.reason, "off_topic")
        self.assertIn("news context", out.message)

    @patch("graph.get_classifier_model")
    def test_classifier_omits_article_chunks(self, mock_get_classifier: MagicMock) -> None:
        structured = MagicMock()
        structured.invoke.return_value = ScopeDecision(allowed=False, reason="off_topic")
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        from chat import run_chat

        run_chat(self._request("Write me a poem"))

        invoke_args = structured.invoke.call_args[0][0]
        human = invoke_args[1].content
        self.assertIn("user_message:", human)
        self.assertNotIn("Summit ends", human)
        self.assertNotIn("Leaders agreed on a draft", human)

    @patch("graph.get_answer_model")
    @patch("graph.get_classifier_model")
    def test_allow_calls_answer(
        self,
        mock_get_classifier: MagicMock,
        mock_get_answer: MagicMock,
    ) -> None:
        structured = MagicMock()
        structured.invoke.return_value = ScopeDecision(allowed=True, reason="ok")
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        tool_bound = MagicMock()
        tool_bound.invoke.return_value = AIMessage(content="thinking", tool_calls=[])
        answer_structured = MagicMock()
        answer_structured.invoke.return_value = AnswerPayload(
            reply="Leaders agreed on a draft per BBC.",
            citations=[
                ChatCitation(
                    article_id=9,
                    title="Summit ends",
                    url="https://example.com/summit",
                )
            ],
        )
        model = MagicMock()
        model.bind_tools.return_value = tool_bound
        model.with_structured_output.return_value = answer_structured
        mock_get_answer.return_value = model

        from chat import run_chat

        out = run_chat(self._request())
        self.assertFalse(out.refused)
        self.assertEqual(out.reason, "ok")
        self.assertIn("draft", out.reply)
        self.assertEqual(len(out.citations), 1)
        self.assertEqual(out.citations[0].article_id, 9)

        human = tool_bound.invoke.call_args[0][0][1].content
        self.assertIn("<<<DATA>>>", human)
        self.assertIn("article_id: 9", human)

    @patch("graph._tool_node")
    @patch("graph.get_answer_model")
    @patch("graph.get_classifier_model")
    def test_tool_round_then_answer(
        self,
        mock_get_classifier: MagicMock,
        mock_get_answer: MagicMock,
        mock_tool_node: MagicMock,
    ) -> None:
        structured = MagicMock()
        structured.invoke.return_value = ScopeDecision(allowed=True, reason="ok")
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        mock_tool_node.invoke.return_value = {
            "messages": [
                ToolMessage(
                    content=(
                        "<<<DATA>>>\narticle_id: 3\ntitle: Extra coverage\n"
                        "url: https://example.com/extra\n<<<END_DATA>>>"
                    ),
                    tool_call_id="call_1",
                )
            ],
            "known_by_id": {
                9: ContextChunk(
                    article_id=9,
                    title="Summit ends",
                    url="https://example.com/summit",
                ),
                3: ContextChunk(
                    article_id=3,
                    title="Extra coverage",
                    url="https://example.com/extra",
                ),
            },
            "searched_ids": [3],
        }

        tool_bound = MagicMock()
        tool_bound.invoke.side_effect = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_articles",
                        "id": "call_1",
                        "args": {"query": "extra coverage"},
                    }
                ],
            ),
            AIMessage(content="done", tool_calls=[]),
        ]
        answer_structured = MagicMock()
        answer_structured.invoke.return_value = AnswerPayload(
            reply="There was extra coverage.",
            citations=[],
        )
        model = MagicMock()
        model.bind_tools.return_value = tool_bound
        model.with_structured_output.return_value = answer_structured
        mock_get_answer.return_value = model

        from chat import run_chat

        out = run_chat(self._request("Anything else?"))
        self.assertFalse(out.refused)
        self.assertIn("extra coverage", out.reply.lower())
        mock_tool_node.invoke.assert_called()
        # Empty model citations → fall back to searched_ids
        self.assertTrue(any(c.article_id == 3 for c in out.citations))


class HandlerTests(unittest.TestCase):
    @patch("main.run_chat")
    def test_handler_dict_roundtrip(self, mock_run: MagicMock) -> None:
        from n2s_api import ChatWorkerResponse

        from main import handler

        mock_run.return_value = ChatWorkerResponse(
            refused=False,
            reason="ok",
            reply="Hello",
            citations=[],
        )
        payload = {
            "scope": "brief",
            "user_id": 1,
            "message": "What is new?",
            "history": [],
            "chunks": [],
        }
        out = handler(payload)
        self.assertEqual(out["reply"], "Hello")
        self.assertFalse(out["refused"])
        self.assertEqual(out["citations"], [])

    def test_handler_invalid_payload(self) -> None:
        from main import handler

        out = handler({"scope": "brief", "message": ""})
        self.assertTrue(out["refused"])


if __name__ == "__main__":
    unittest.main()
