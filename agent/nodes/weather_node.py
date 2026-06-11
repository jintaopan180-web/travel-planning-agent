from typing import Any

from agent.nodes.common import append_trace, build_node_agent, safe_run_node_agent
from agent.schemas import WeatherResult, model_to_dict, parse_model_from_text


WEATHER_NODE_PROMPT = """
你是旅行规划工作流中的天气查询节点。
职责：只根据用户旅行需求查询或整理目的地天气、天气风险和出行提醒。
如果可以使用高德 MCP 天气工具，优先调用工具；如果工具不可用，说明天气信息暂不可实时确认。
不要生成完整旅行计划，也不要处理公交或打车方案。
请只输出 JSON，字段包括：summary、source、status、suggestions。
""".strip()

_weather_agent = None


def get_weather_agent():
    global _weather_agent
    if _weather_agent is None:
        _weather_agent = build_node_agent(WEATHER_NODE_PROMPT)
    return _weather_agent


async def weather_node(state: dict[str, Any]) -> dict[str, Any]:
    """天气节点：将天气查询结果写入 TravelState.weather。"""
    query = f"""
用户原始需求：{state.get("user_query", "")}
目的地城市：{state.get("destination", "")}
出行日期或时间：{state.get("travel_date") or "未提供"}
游玩天数：{state.get("travel_days") or "未提供"}
偏好：{state.get("preferences", [])}
""".strip()
    result, run_error = await safe_run_node_agent(get_weather_agent(), query, "weather_node")

    errors: list[str] = []
    if run_error:
        errors.append(run_error)
        weather = model_to_dict(
            WeatherResult(
                status="degraded",
                source="weather_node",
                summary="天气暂不可实时确认，建议同时准备晴天和雨天两套出行方案。",
                suggestions=["准备雨具", "保留室内备选景点"],
            )
        )
    else:
        # LLM 输出格式不稳定时，先抽取 JSON，再用 Pydantic 校验；失败则保留原文摘要。
        weather, parse_error = parse_model_from_text(
            WeatherResult,
            result,
            {
                "summary": result or "天气暂不可实时确认。",
                "source": "weather_node",
                "status": "degraded",
                "suggestions": ["准备晴雨两套方案"],
            },
        )
        if parse_error:
            errors.append(parse_error)

    return {
        "weather": weather,
        "errors": errors,
        "node_trace": append_trace(state, "weather_node"),
    }
