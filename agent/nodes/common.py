from typing import Any

from langchain.agents import create_agent

from agent.tools.agent_tools import get_agent_tools
from agent.tools.middleware import log_before_model, monitor_tool
from model.factory import chat_model
from utils.logger_handler import logger


def append_trace(state: dict[str, Any], node_name: str) -> list[str]:
    """
    返回当前节点的追踪片段。

    node_trace 在 TravelState 里配置了 reducer，LangGraph 会负责把各节点
    返回的列表合并到全局 state；这里不要再手动带上旧 trace，避免并行分支重复。
    """
    return [node_name]


def build_node_agent(system_prompt: str, include_tools: bool = True):
    """为每个节点创建职责单一的 Agent，底层仍复用现有模型和 MCP 工具。"""
    return create_agent(
        model=chat_model,
        system_prompt=system_prompt,
        tools=get_agent_tools(include_mcp=include_tools),
        middleware=[monitor_tool, log_before_model],
    )


async def run_node_agent(agent: Any, user_content: str) -> str:
    """执行节点 Agent，并提取最后一条模型回复文本。"""
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": user_content,
                }
            ]
        }
    )
    messages = result.get("messages") or []
    if not messages:
        return ""

    content = getattr(messages[-1], "content", "")
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


async def safe_run_node_agent(
    agent: Any,
    user_content: str,
    node_name: str,
) -> tuple[str, str | None]:
    """节点级异常降级入口：Agent 失败时返回错误文本，而不是中断 StateGraph。"""
    try:
        return await run_node_agent(agent, user_content), None
    except Exception as exc:
        logger.error(f"[{node_name}] 节点执行失败，已降级：{exc}", exc_info=True)
        return "", f"{node_name} 执行失败：{exc}"
