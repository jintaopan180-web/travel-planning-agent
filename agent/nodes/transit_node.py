from typing import Any

from agent.nodes.common import append_trace, build_node_agent, safe_run_node_agent
from agent.schemas import TransitRoute, model_to_dict, parse_model_from_text


TRANSIT_NODE_PROMPT = """
你是旅行规划工作流中的公交路线规划节点。
职责：只根据用户旅行需求规划公共交通路线，关注地铁、公交、步行衔接、换乘和耗时。
如果可以使用高德 MCP 公交或路线工具，优先调用工具；如果信息不足，说明需要补充起终点。
不要生成完整旅行计划，也不要处理打车方案。
请只输出 JSON，字段包括：origin、destination、duration_minutes、cost_yuan、transfers、walking_distance_meters、summary、source、status。
""".strip()

_transit_agent = None


def get_transit_agent():
    global _transit_agent
    if _transit_agent is None:
        _transit_agent = build_node_agent(TRANSIT_NODE_PROMPT)
    return _transit_agent


async def transit_node(state: dict[str, Any]) -> dict[str, Any]:
    """公交节点：将公交规划结果写入 TravelState.transit_routes。"""
    query = f"""
用户原始需求：{state.get("user_query", "")}
目的地城市：{state.get("destination", "")}
明确出发地：{state.get("origin") or "未提供"}
想去的地方：{state.get("must_see_places", [])}
游玩天数：{state.get("travel_days") or "未提供"}
偏好：{state.get("preferences", [])}

如果用户没有提供城市内每日起点/终点，不要要求用户补充每一段路线；
请根据目的地城市、想去地点和常规旅游动线，整理可执行的公共交通建议。
""".strip()
    result, run_error = await safe_run_node_agent(get_transit_agent(), query, "transit_node")

    errors: list[str] = []
    if run_error:
        errors.append(run_error)
        route = model_to_dict(
            TransitRoute(
                status="degraded",
                source="transit_node",
                summary="公交路线暂不可用，建议优先查看打车方案或在出发前重新查询实时公交。",
            )
        )
    else:
        # 先做 JSON 提取和 Pydantic 校验，失败时保留原始摘要作为降级路线。
        route, parse_error = parse_model_from_text(
            TransitRoute,
            result,
            {
                "summary": result or "公交路线暂不可用。",
                "source": "transit_node",
                "status": "degraded",
            },
        )
        if parse_error:
            errors.append(parse_error)

    return {
        "transit_routes": [route],
        "errors": errors,
        "node_trace": append_trace(state, "transit_node"),
    }
