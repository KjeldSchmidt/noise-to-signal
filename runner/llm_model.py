from langchain.chat_models import init_chat_model

_model = None


def get_model():
    global _model
    if _model is None:
        _model = init_model()

    return _model


def init_model():
    model = init_chat_model(
        "eu.amazon.nova-lite-v1:0",
        model_provider="bedrock_converse",
        region_name="eu-central-1",
    )
    return model
