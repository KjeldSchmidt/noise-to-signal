from unittest.mock import MagicMock, patch

from embed import build_embed_input, embed_text


def test_build_embed_input_joins_title_and_summary() -> None:
    assert build_embed_input(title="Hello", summary="World") == "Hello\n\nWorld"
    assert build_embed_input(title="Hello", summary="") == "Hello"
    assert build_embed_input(title="", summary="World") == "World"


@patch("embed.get_embeddings")
def test_embed_text_uses_langchain_embeddings(mock_get: MagicMock) -> None:
    vector = [0.01] * 1024
    mock_embeddings = MagicMock()
    mock_embeddings.embed_documents.return_value = [vector]
    mock_get.return_value = mock_embeddings

    out = embed_text("hello world")
    assert len(out) == 1024
    mock_get.assert_called_once_with(input_type="clustering")
    mock_embeddings.embed_documents.assert_called_once_with(["hello world"])
