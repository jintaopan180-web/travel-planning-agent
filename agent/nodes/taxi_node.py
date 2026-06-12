from typing import Any

from agent.nodes.common import append_trace, build_node_agent, safe_run_node_agent
from agent.schemas import TaxiRoute, model_to_dict, parse_model_from_text


TAXI_NODE_PROMPT = """
你是旅行规划工作流中的打车方案节点。
职责：只根据用户旅行需求整理打车路线、预估耗时、距离、费用和适用场景。
如果可以使用高德 MCP 打车或路线工具，优先调用工具；如果工具没有实时价格，明确说明费用仅能估算。
不要生成完整旅行计划，也不要处理公交方案。
请只输出 JSON，字段包括：origin、destination、duration_minutes、distance_km、estimated_cost_yuan、summary、source、status。
""".strip()

_taxi_agent = None


def get_taxi_agent():
    global _taxi_agent
    if _taxi_agent is None:
        _taxi_agent = build_node_agent(TAXI_NODE_PROMPT)
    return _taxi_agent


async def taxi_node(state: dict[str, Any]) -> dict[str, Any]:
    """打车节点：将打车规划结果写入 TravelState.taxi_routes。"""
    query = state.get("user_query", "")
    result, run_error = await safe_run_node_agent(get_taxi_agent(), query, "taxi_node")

    errors: list[str] = []
    if run_error:
        errors.append(run_error)
        route = model_to_dict(
            TaxiRoute(
                status="degraded",
                source="taxi_node",
                summary="打车方案暂不可用，费用需以平台实时价格为准，可优先参考公交方案。",
            )
        )
    else:
        # 先做 JSON 提取和 Pydantic 校验，失败时保留原始摘要作为降级路线。
        route, parse_error = parse_model_from_text(
            TaxiRoute,
            result,
            {
                "summary": result or "打车方案暂不可用，费用需以平台实时价格为准。",
                "source": "taxi_node",
                "status": "degraded",
            },
        )
        if parse_error:
            errors.append(parse_error)

    return {
        "taxi_routes": [route],
        "errors": errors,
        "node_trace": append_trace(state, "taxi_node"),
    }
