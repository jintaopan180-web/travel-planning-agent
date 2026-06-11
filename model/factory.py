import os

from langchain_community.chat_models.tongyi import ChatTongyi


DEFAULT_CHAT_MODEL_NAME = "qwen3.7-max"
CHAT_MODEL_NAME_ENV = "CHAT_MODEL_NAME"


def get_chat_model_name() -> str:
    """读取聊天模型名；默认使用 qwen3.7-max，也可通过 CHAT_MODEL_NAME 环境变量覆盖。"""
    return os.getenv(CHAT_MODEL_NAME_ENV, DEFAULT_CHAT_MODEL_NAME).strip() or DEFAULT_CHAT_MODEL_NAME


# 模块级单例：所有节点复用同一个聊天模型实例。
chat_model = ChatTongyi(model=get_chat_model_name())
