"""Unit tests for news_chat classifier + answer assembly (mocked models)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from n2s_api import ChatHistoryMessage, ChatWorkerRequest, ContextChunk

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

    def test_topic_digest_omits_summaries(self) -> None:
        chunks = [
            ContextChunk(
                article_id=1,
                title="Gaza hospital strike",
                source="BBC",
                place_label="Gaza",
                story_label="Hospital attack",
                summary="Long summary that must not appear in the digest.",
            ),
            ContextChunk(
                article_id=2,
                title="Second piece",
                source="NPR",
                summary="Also hidden.",
            ),
        ]
        digest = prompts.topic_digest(chunks)
        self.assertIn("Gaza hospital strike | BBC | Gaza | Hospital attack", digest)
        self.assertIn("Second piece | NPR", digest)
        self.assertNotIn("Long summary", digest)
        self.assertNotIn("Also hidden", digest)

    def test_topic_digest_empty(self) -> None:
        self.assertEqual(prompts.topic_digest([]), "(no articles in scope)")


class ChatPipelineTests(unittest.TestCase):
    def _request(self, message: str = "What happened?") -> ChatWorkerRequest:
        return ChatWorkerRequest(
            scope="brief",
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
    def test_classifier_receives_topic_digest(self, mock_get_classifier: MagicMock) -> None:
        structured = MagicMock()
        structured.invoke.return_value = chat_mod.ScopeDecision(allowed=False, reason="off_topic")
        mock_get_classifier.return_value.with_structured_output.return_value = structured

        chat_mod.run_chat(self._request("Write me a poem"))

        invoke_args = structured.invoke.call_args[0][0]
        human = invoke_args[1].content
        self.assertIn("topic_digest:", human)
        self.assertIn("Summit ends | BBC | Geneva | Climate summit", human)
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

        answer = MagicMock()
        answer.content = "Leaders agreed on a draft per BBC."
        mock_get_answer.return_value.invoke.return_value = answer

        out = chat_mod.run_chat(self._request())
        self.assertFalse(out.refused)
        self.assertEqual(out.reason, "ok")
        self.assertIn("draft", out.reply)

        invoke_args = mock_get_answer.return_value.invoke.call_args[0][0]
        human = invoke_args[1].content
        self.assertIn("<<<DATA>>>", human)
        self.assertIn("Summit ends", human)


class HandlerTests(unittest.TestCase):
    @patch("main.run_chat")
    def test_handler_dict_roundtrip(self, mock_run: MagicMock) -> None:
        from n2s_api import ChatWorkerResponse

        from main import handler

        mock_run.return_value = ChatWorkerResponse(
            refused=False,
            reason="ok",
            reply="Hello",
        )
        payload = {
            "scope": "brief",
            "message": "What is new?",
            "history": [],
            "chunks": [],
        }
        out = handler(payload)
        self.assertEqual(out["reply"], "Hello")
        self.assertFalse(out["refused"])

    def test_handler_invalid_payload(self) -> None:
        from main import handler

        out = handler({"scope": "brief", "message": ""})
        self.assertTrue(out["refused"])


if __name__ == "__main__":
    unittest.main()
