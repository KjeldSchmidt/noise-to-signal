"""Unit tests for news_chat classifier + answer assembly (mocked models)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from n2s_api import ChatCitation, ChatHistoryMessage, ChatWorkerRequest, ContextChunk

import chat as chat_mod
import prompts


class PromptsTests(unittest.TestCase):
    def test_format_chunk_uses_data_delimiters(self) -> None:
        chunk = ContextChunk(
            article_id=1,
            title="Floods",
            source="NPR",
            summary="Water rising.",
        )
        text = prompts.format_chunk(chunk)
        self.assertIn("<<<DATA>>>", text)
        self.assertIn("<<<END_DATA>>>", text)
        self.assertIn("Floods", text)
        self.assertIn("NPR", text)


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

    @patch("chat.get_classifier_model")
    def test_refuse_off_topic(self, mock_get_classifier: MagicMock) -> None:
        structured = MagicMock()
        structured.invoke.return_value = chat_mod.ScopeDecision(
            allowed=False,
            reason="off_topic",
        )
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        with patch("chat.answer_request") as mock_answer:
            out = chat_mod.run_chat(self._request("Write me a poem"))
            mock_answer.assert_not_called()

        self.assertTrue(out.refused)
        self.assertEqual(out.reason, "off_topic")
        self.assertIn("news context", out.message)

    @patch("chat.get_classifier_model")
    def test_classifier_omits_article_chunks(self, mock_get_classifier: MagicMock) -> None:
        structured = MagicMock()
        structured.invoke.return_value = chat_mod.ScopeDecision(allowed=False, reason="off_topic")
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        chat_mod.run_chat(self._request("Write me a poem"))

        invoke_args = structured.invoke.call_args[0][0]
        human = invoke_args[1].content
        self.assertIn("user_message:", human)
        self.assertNotIn("topic_digest:", human)
        self.assertNotIn("Summit ends", human)
        self.assertNotIn("Leaders agreed on a draft", human)

    @patch("chat.get_answer_model")
    @patch("chat.get_classifier_model")
    def test_allow_calls_answer(
        self,
        mock_get_classifier: MagicMock,
        mock_get_answer: MagicMock,
    ) -> None:
        structured = MagicMock()
        structured.invoke.return_value = chat_mod.ScopeDecision(allowed=True, reason="ok")
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        tool_bound = MagicMock()
        tool_bound.invoke.return_value = AIMessage(content="thinking", tool_calls=[])
        answer_structured = MagicMock()
        answer_structured.invoke.return_value = chat_mod.AnswerPayload(
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

        out = chat_mod.run_chat(self._request())
        self.assertFalse(out.refused)
        self.assertEqual(out.reason, "ok")
        self.assertIn("draft", out.reply)
        self.assertEqual(len(out.citations), 1)
        self.assertEqual(out.citations[0].article_id, 9)

        human = tool_bound.invoke.call_args[0][0][1].content
        self.assertIn("<<<DATA>>>", human)
        self.assertIn("Summit ends", human)

    @patch("chat.make_search_articles_tool")
    @patch("chat.get_answer_model")
    @patch("chat.get_classifier_model")
    def test_tool_round_then_answer(
        self,
        mock_get_classifier: MagicMock,
        mock_get_answer: MagicMock,
        mock_make_tool: MagicMock,
    ) -> None:
        structured = MagicMock()
        structured.invoke.return_value = chat_mod.ScopeDecision(allowed=True, reason="ok")
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        tool = MagicMock()
        tool.name = "search_articles"
        tool.invoke.return_value = (
            "<<<DATA>>>\ntitle: Extra coverage\nurl: https://example.com/extra\n<<<END_DATA>>>"
        )
        mock_make_tool.return_value = tool

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
        answer_structured.invoke.return_value = chat_mod.AnswerPayload(
            reply="There was extra coverage.",
            citations=[],
        )
        model = MagicMock()
        model.bind_tools.return_value = tool_bound
        model.with_structured_output.return_value = answer_structured
        mock_get_answer.return_value = model

        out = chat_mod.run_chat(self._request("Anything else?"))
        self.assertFalse(out.refused)
        self.assertIn("extra coverage", out.reply.lower())
        tool.invoke.assert_called()
        mock_make_tool.assert_called_once()


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
