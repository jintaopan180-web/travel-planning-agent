import os

from langchain_community.chat_models.tongyi import ChatTongyi


DEFAULT_CHAT_MODEL_NAME = "qwen3-max"
CHAT_MODEL_NAME_ENV = "CHAT_MODEL_NAME"


def get_chat_model_name() -> str:
    """Read the chat model name from environment variables, falling back to Qwen."""
    return os.getenv(CHAT_MODEL_NAME_ENV, DEFAULT_CHAT_MODEL_NAME).strip() or DEFAULT_CHAT_MODEL_NAME


# Module-level singleton used by all Agent nodes.
chat_model = ChatTongyi(model=get_chat_model_name())
