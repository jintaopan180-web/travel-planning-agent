import asyncio
import os
import threading
from collections.abc import Coroutine
from typing import Any

from utils.config_handler import agent_conf
from utils.logger_handler import logger


AMAP_MCP_URL_ENV = "AMAP_MCP_URL"
AMAP_MCP_SERVER_NAME = "amap_maps"
AMAP_MCP_LOAD_TIMEOUT_SECONDS = 15

_amap_mcp_tools_cache: list[Any] | None = None
_amap_mcp_tools_cache_url: str | None = None


def _get_amap_mcp_url() -> str:
    """Read the AMap MCP URL from environment variables or config/agent.yml."""
    url = os.getenv(AMAP_MCP_URL_ENV)
    if not url:
        url = (agent_conf or {}).get("amap_mcp_url")

    if not isinstance(url, str):
        return ""

    url = url.strip()
    if not url or url.startswith("${"):
        return ""

    return url


async def load_amap_mcp_tools_async() -> list[Any]:
    """Load AMap MCP tools and convert them into LangChain-compatible tools."""
    global _amap_mcp_tools_cache, _amap_mcp_tools_cache_url

    amap_mcp_url = _get_amap_mcp_url()
    if not amap_mcp_url:
        logger.info(
            f"[amap_mcp] 未配置高德 MCP URL，跳过加载。可设置环境变量 {AMAP_MCP_URL_ENV} "
            "或 config/agent.yml 中的 amap_mcp_url"
        )
        return []

    if _amap_mcp_tools_cache is not None and _amap_mcp_tools_cache_url == amap_mcp_url:
        return _amap_mcp_tools_cache

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning("[amap_mcp] 未安装 langchain-mcp-adapters，无法加载高德 MCP tools")
        return []

    try:
        client = MultiServerMCPClient(
            {
                AMAP_MCP_SERVER_NAME: {
                    "transport": "http",
                    "url": amap_mcp_url,
                }
            },
            tool_name_prefix=True,
        )
        tools = await asyncio.wait_for(
            client.get_tools(),
            timeout=AMAP_MCP_LOAD_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            f"[amap_mcp] 高德 MCP tools 加载超时（>{AMAP_MCP_LOAD_TIMEOUT_SECONDS}s），已跳过"
        )
        return []
    except Exception as exc:
        logger.warning(f"[amap_mcp] 高德 MCP tools 加载失败：{exc}", exc_info=True)
        return []

    _amap_mcp_tools_cache = tools
    _amap_mcp_tools_cache_url = amap_mcp_url

    tool_names = ", ".join(getattr(tool_item, "name", "<unknown>") for tool_item in tools)
    logger.info(f"[amap_mcp] 已动态加载 {len(tools)} 个高德 MCP tools：{tool_names}")
    return tools


def _run_coroutine(coro: Coroutine[Any, Any, list[Any]]) -> list[Any]:
    """Run an async tool-loading coroutine from sync or already-async contexts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[Any] = []
    error: BaseException | None = None

    def runner():
        nonlocal result, error
        try:
            result = asyncio.run(coro)
        except BaseException as exc:
            error = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if error is not None:
        raise error

    return result


def _dedupe_tools(tools: list[Any]) -> list[Any]:
    """Deduplicate tools by tool name while preserving first-seen order."""
    unique_tools = []
    seen_names = set()

    for tool_item in tools:
        tool_name = getattr(tool_item, "name", None)
        if tool_name and tool_name in seen_names:
            logger.warning(f"[agent_tools] 工具名重复，已跳过：{tool_name}")
            continue

        if tool_name:
            seen_names.add(tool_name)

        unique_tools.append(tool_item)

    return unique_tools


def get_agent_tools(include_mcp: bool = True) -> list[Any]:
    """
    Return the tools available to the travel planning Agent.

    The travel planning Agent currently exposes only AMap MCP tools.
    """
    tools: list[Any] = []

    if include_mcp:
        tools.extend(_run_coroutine(load_amap_mcp_tools_async()))

    return _dedupe_tools(tools)
