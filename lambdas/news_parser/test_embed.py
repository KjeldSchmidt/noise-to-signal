from unittest.mock import MagicMock, patch

from embed import build_embed_input, embed_text


def test_build_embed_input_joins_title_and_summary() -> None:
    assert build_embed_input(title="Hello", summary="World") == "Hello\n\nWorld"
    assert build_embed_input(title="Hello", summary="") == "Hello"
    assert build_embed_input(title="", summary="World") == "World"


@patch("embed.boto3.client")
def test_embed_text_parses_bedrock_response(mock_client: MagicMock) -> None:
    vector = [0.01] * 1024
    body = MagicMock()
    body.read.return_value = b'{"embeddings": [' + str(vector).encode() + b"]}"
    # JSON needs proper floats — rebuild with json
    import json

    body.read.return_value = json.dumps({"embeddings": [vector]}).encode()
    mock_client.return_value.invoke_model.return_value = {"body": body}

    out = embed_text("hello world")
    assert len(out) == 1024
    mock_client.return_value.invoke_model.assert_called_once()
    kwargs = mock_client.return_value.invoke_model.call_args.kwargs
    assert kwargs["modelId"] == "cohere.embed-multilingual-v3"
