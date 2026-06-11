import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import before_model, wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from agent.tools.fallbacks import get_tool_fallback_response
from utils.logger_handler import logger


def _preview_content(content: Any, max_length: int = 500) -> str:
    """日志安全预览：将字符串/列表/字典截断为适合日志输出的简短文本，替换换行符防止日志换行。"""
    if content is None:
        return ""

    if isinstance(content, str):
        preview = content
    else:
        try:
            preview = json.dumps(content, ensure_ascii=False, default=str)
        except TypeError:
            preview = str(content)

    preview = preview.replace("\n", "\\n")
    if len(preview) > max_length:
        return preview[:max_length] + "..."
    return preview


@wrap_tool_call
async def monitor_tool(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
) -> ToolMessage | Command[Any]:
    """
    工具调用包装中间件：记录每次工具调用的入参/结果，并在工具调用抛出异常时自动降级。

    执行流程：
      1. 记录调用日志（工具名 + 参数预览）
      2. 执行真正的工具调用 handler(request)
      3. 成功 → 记录成功日志，返回原始结果
      4. 失败 → 记录错误日志，调用 fallbacks.get_tool_fallback_response
         获取三级兜底数据，构造一个 content 为兜底文本的 ToolMessage 返回，
         避免 Agent 因单个工具失败而整体中断。
    """
    tool_call = request.tool_call or {}
    tool_name = tool_call.get("name", "<unknown>")
    tool_args = tool_call.get("args", {})

    logger.info(f"[tool monitor] calling tool: {tool_name}")
    logger.info(f"[tool monitor] tool args: {_preview_content(tool_args)}")

    try:
        result = await handler(request)
    except Exception as exc:
        logger.error(f"[tool monitor] tool failed: {tool_name}; reason: {exc}", exc_info=True)
        fallback_content = get_tool_fallback_response(tool_name, tool_args, str(exc))
        logger.warning(f"[tool monitor] tool fallback used: {tool_name}")
        return ToolMessage(
            content=fallback_content,
            name=tool_name,
            tool_call_id=tool_call.get("id", "fallback_tool_call"),
        )

    logger.info(f"[tool monitor] tool succeeded: {tool_name}")
    return result


@before_model
def log_before_model(
    state: AgentState,
    runtime: Runtime,
) -> None:
    """
    模型调用前中间件：每次 LLM 推理前记录当前消息上下文。

    记录消息总数 + 最新一条消息的类型和内容预览，便于排查 Agent 推理链中的异常。
    """
    messages = state.get("messages", [])
    logger.info(f"[log_before_model] about to call model with {len(messages)} messages")

    if messages:
        latest_message = messages[-1]
        latest_type = type(latest_message).__name__
        latest_content = getattr(latest_message, "content", "")
        logger.debug(
            f"[log_before_model] latest message: {latest_type} | "
            f"{_preview_content(latest_content)}"
        )

    return None
