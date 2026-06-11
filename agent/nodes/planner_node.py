from typing import Any

from agent.nodes.common import append_trace, build_node_agent, safe_run_node_agent


PLANNER_NODE_PROMPT = """
你是旅行规划工作流中的统筹规划节点。
职责：汇总天气、公交和打车节点结果，生成用户可读的最终旅行规划。
第一阶段只做信息汇总和表达组织，不直接补查 MCP，也不引入结构化经济性打分。
输出需要包含：每日安排、天气影响、公交方案、打车方案和简要建议。
如果用户只提供城市和几个想去的地方，请自行规划每天的景点顺序、城市内起终点和交通衔接，不要把这些都推回给用户。
如果某个节点 status=degraded 或 errors 中存在失败信息，不要中断输出；请明确说明该部分为降级结果。
""".strip()

_planner_agent = None


def get_planner_agent():
    global _planner_agent
    if _planner_agent is None:
        # 统筹节点默认只读前序节点结果，不重复调用 MCP。
        _planner_agent = build_node_agent(PLANNER_NODE_PROMPT, include_tools=False)
    return _planner_agent



def _build_static_plan(state: dict[str, Any]) -> str:
    """planner 自身失败时的最后降级方案，保证用户仍能得到可用文本。"""
    weather = state.get("weather", {}) or {}
    transit_routes = state.get("transit_routes", []) or []
    taxi_routes = state.get("taxi_routes", []) or []
    errors = state.get("errors", []) or []

    transit_summary = transit_routes[0].get("summary", "公交路线暂不可用。") if transit_routes else "公交路线暂不可用。"
    taxi_summary = taxi_routes[0].get("summary", "打车方案暂不可用，费用需以平台实时价格为准。") if taxi_routes else "打车方案暂不可用，费用需以平台实时价格为准。"

    return f"""
旅行规划降级版

用户需求：{state.get("user_query", "")}

每日安排：
- 先围绕核心景点安排半日到一日游，优先选择距离较近的景点组合。
- 天气或交通不确定时，保留一个室内备选点，并把长距离移动放在白天完成。
- 如果用户只提供城市和想去的地方，城市内每日起终点和景点顺序由规划器自行安排。

天气影响：
{weather.get("summary", "天气暂不可实时确认，建议准备晴天和雨天两套方案。")}

公交方案：
{transit_summary}

打车方案：
{taxi_summary}

简要建议：
- 预算优先时，优先使用公交或地铁。
- 时间优先、天气较差或携带行李时，优先打车。
- 以下信息来自降级流程，出发前建议重新确认实时天气和交通：{errors or "暂无额外错误信息"}
""".strip()


async def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """统筹节点：读取 TravelState 中的结构化字段，生成最终行程输出。"""
    user_query = state.get("user_query", "")
    content = f"""
用户原始需求：
{user_query}

目的地：
{state.get("destination", "") or "待解析"}

出发地：
{state.get("origin") or "未提供"}

出行天数：
{state.get("travel_days") or "未提供"}

出行日期或时间：
{state.get("travel_date") or "未提供"}

想去的地方：
{state.get("must_see_places", [])}

偏好：
{state.get("preferences", [])}

天气节点结果：
{state.get("weather", {})}

公交节点结果：
{state.get("transit_routes", [])}

    打车节点结果：
{state.get("taxi_routes", [])}

已记录的异常或降级信息：
{state.get("errors", [])}
""".strip()

    result, run_error = await safe_run_node_agent(get_planner_agent(), content, "planner_node")
    errors = [run_error] if run_error else []
    final_plan = result or _build_static_plan(state)

    return {
        # 第二步只保证 route_comparison 字段存在，具体经济性对比留到第三步。
        "route_comparison": state.get("route_comparison", {}),
        "final_plan": final_plan,
        "errors": errors,
        "node_trace": append_trace(state, "planner_node"),
    }
