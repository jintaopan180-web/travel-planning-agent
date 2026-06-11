import asyncio
import re
import threading
from queue import Queue
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes import planner_node, taxi_node, transit_node, weather_node
from agent.nodes.common import append_trace
from agent.schemas import TravelRequirements, extract_json_payload, model_to_dict
from agent.state import TravelState
from model.factory import chat_model
from utils.logger_handler import logger


REQUIREMENTS_EXTRACT_PROMPT = """
你是旅游规划 Agent 的需求解析节点。
请从用户输入中抽取结构化旅游需求，只输出 JSON，不要输出解释。

字段：
- destination：用户明确提到的主要旅行城市或目的地城市；没有明确城市则为空字符串，不要根据景点自行推断城市。
- origin：用户明确提到的出发城市/出发地点；没有明确提到则为 null。
- travel_days：明确的游玩天数，整数；没有则为 null。
- travel_date：明确的日期、月份、季节或“明天/周末”等时间表达；没有则为 null。
- must_see_places：用户明确想去的景点、商圈、餐厅、咖啡馆、博物馆等地点列表。
- preferences：用户偏好，例如自然风景、咖啡、亲子、少走路、预算低、慢节奏。
- confidence：0 到 1，表示你对抽取结果的置信度。

重要规则：
- 城市内每天的起点、终点、景点顺序通常应由 Agent 自动规划，不要因为缺少酒店、每日起点或每段路线终点就判定需求缺失。
- origin 只在用户明确说“从上海出发”“我在西湖附近”等情况填写；不要编造。
- 不要把“喜欢咖啡”误认为必须去的具体地点，除非用户给出明确店名。
""".strip()


COMMON_CITY_NAMES = (
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "苏州",
    "南京",
    "成都",
    "重庆",
    "西安",
    "武汉",
    "长沙",
    "厦门",
    "青岛",
    "天津",
    "大理",
    "丽江",
    "三亚",
    "桂林",
    "昆明",
    "洛阳",
    "开封",
)

CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def _parse_days_from_text(text: str) -> int | None:
    match = re.search(
        r"(?:玩|游玩|旅行|旅游|行程|安排|规划)?\s*(\d+|[一二两三四五六七八九十])\s*(?:天|日游|日行程)",
        text,
    )
    if not match:
        return None

    value = match.group(1)
    if value.isdigit():
        return int(value)
    return CHINESE_DIGITS.get(value)


def _heuristic_extract_requirements(user_query: str) -> dict[str, Any]:
    """LLM 解析失败时的轻量兜底，只匹配用户明确写出的城市名。"""
    destination = ""
    for city in COMMON_CITY_NAMES:
        if city in user_query:
            destination = city
            break

    preferences = []
    for keyword in ("自然", "咖啡", "博物馆", "亲子", "美食", "慢节奏", "少走路", "预算低", "拍照"):
        if keyword in user_query:
            preferences.append(keyword)

    return model_to_dict(
        TravelRequirements(
            destination=destination,
            travel_days=_parse_days_from_text(user_query),
            preferences=preferences,
            confidence=0.35 if destination or preferences else 0.0,
        )
    )


async def _extract_requirements(user_query: str) -> tuple[dict[str, Any], str | None]:
    try:
        response = await chat_model.ainvoke(
            [
                {"role": "system", "content": REQUIREMENTS_EXTRACT_PROMPT},
                {"role": "user", "content": user_query},
            ]
        )
        payload = extract_json_payload(_message_content(response))
        if isinstance(payload, list):
            payload = payload[0] if payload else {}

        requirements = TravelRequirements(**payload)
        return model_to_dict(requirements), None
    except Exception as exc:
        logger.warning(f"[parse_requirements] LLM 需求解析失败，使用启发式兜底：{exc}", exc_info=True)
        return _heuristic_extract_requirements(user_query), f"需求解析降级：{exc}"


def _build_clarification_question(requirements: dict[str, Any], missing_fields: list[str]) -> str:
    examples = []
    if "destination" in missing_fields:
        examples.append("旅行城市")
    if "travel_days" in missing_fields:
        examples.append("游玩天数")

    destination = requirements.get("destination") or "这个城市"
    if missing_fields == ["travel_days"]:
        return f"为了继续规划，我还需要确认：你准备在{destination}玩几天？也可以顺便补充想去的地方、预算或节奏偏好。"

    if missing_fields == ["destination"]:
        return "为了继续规划，我还需要确认：你想去哪个城市？如果已经有想去的几个地方，也可以一起告诉我。"

    fields = "、".join(examples)
    return f"为了继续规划，我还需要确认：{fields}。你可以直接回复类似“杭州，两天，想去西湖、灵隐寺和几家咖啡馆”。"


async def parse_requirements_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    需求解析节点：抽取关键旅游需求，并判断是否需要人机追问。

    旅游场景不强制用户提供城市内每一段路线的起点/终点；只把城市和天数
    作为继续自动规划的关键字段，景点顺序与日内起终点交给后续节点规划。
    """
    user_query = state.get("user_query", "").strip()
    requirements, parse_error = await _extract_requirements(user_query)

    missing_fields = []
    if not requirements.get("destination"):
        missing_fields.append("destination")
    if not requirements.get("travel_days"):
        missing_fields.append("travel_days")

    needs_user_input = bool(missing_fields)
    clarification_question = (
        _build_clarification_question(requirements, missing_fields)
        if needs_user_input
        else ""
    )

    errors = [parse_error] if parse_error else []

    return {
        "destination": requirements.get("destination", ""),
        "origin": requirements.get("origin"),
        "travel_days": requirements.get("travel_days"),
        "travel_date": requirements.get("travel_date"),
        "must_see_places": requirements.get("must_see_places", []),
        "preferences": requirements.get("preferences", []),
        "missing_fields": missing_fields,
        "needs_user_input": needs_user_input,
        "clarification_question": clarification_question,
        "errors": errors,
        "raw": {"requirements": requirements},
        "node_trace": append_trace(state, "parse_requirements_node"),
    }


def route_after_parse(state: dict[str, Any]) -> str:
    """根据需求完整性决定继续自动规划，还是进入人机追问节点。"""
    if state.get("needs_user_input"):
        return "ask_user"
    return "continue_planning"


def ask_user_node(state: dict[str, Any]) -> dict[str, Any]:
    """Human-in-the-loop 节点：把缺失信息转成用户可直接回答的问题。"""
    question = state.get("clarification_question") or "我还需要补充一些信息后才能继续规划。"
    return {
        "final_plan": question,
        "node_trace": append_trace(state, "ask_user_node"),
    }


def continue_planning_node(state: dict[str, Any]) -> dict[str, Any]:
    """需求完整后进入自动规划分支。"""
    return {
        "node_trace": append_trace(state, "continue_planning_node"),
    }


def build_travel_graph():
    """搭建并行 StateGraph：解析后并行查询天气、公交和打车，再汇总规划。"""
    graph = StateGraph(TravelState)

    graph.add_node("parse_requirements", parse_requirements_node)
    graph.add_node("ask_user", ask_user_node)
    graph.add_node("continue_planning", continue_planning_node)
    graph.add_node("weather", weather_node)
    graph.add_node("transit", transit_node)
    graph.add_node("taxi", taxi_node)
    graph.add_node("planner", planner_node)

    graph.add_edge(START, "parse_requirements")

    graph.add_conditional_edges(
        "parse_requirements",
        route_after_parse,
        {
            "ask_user": "ask_user",
            "continue_planning": "continue_planning",
        },
    )
    graph.add_edge("ask_user", END)

    # 需求足够后，三个信息获取节点互不依赖，可以并行执行。
    graph.add_edge("continue_planning", "weather")
    graph.add_edge("continue_planning", "transit")
    graph.add_edge("continue_planning", "taxi")

    # planner 等待 weather/transit/taxi 三个分支都完成后，再读取全局状态汇总。
    graph.add_edge(["weather", "transit", "taxi"], "planner")
    graph.add_edge("planner", END)

    return graph.compile()


class TravelGraphAgent:
    """Streamlit 调用入口：对外保持 execute_stream，同步包装内部异步 StateGraph。"""

    def __init__(self):
        self.graph = build_travel_graph()

    async def _execute_astream(self, query: str):
        # 初始化完整 TravelState，后续节点只更新自己负责的字段。
        initial_state: TravelState = {
            "user_query": query,
            "destination": "",
            "origin": None,
            "travel_days": None,
            "travel_date": None,
            "must_see_places": [],
            "preferences": [],
            "missing_fields": [],
            "needs_user_input": False,
            "clarification_question": "",
            "weather": {},
            "transit_routes": [],
            "taxi_routes": [],
            "route_comparison": {},
            "final_plan": "",
            "node_trace": [],
            "errors": [],
            "raw": {},
        }

        async for state in self.graph.astream(initial_state, stream_mode="values"):
            final_plan = state.get("final_plan")
            if final_plan:
                yield final_plan.strip() + "\n"

    def execute_stream(self, query: str):
        output_queue = Queue()
        stop_signal = object()

        def run_async_stream():
            async def consume_stream():
                async for text in self._execute_astream(query):
                    output_queue.put(text)

            try:
                asyncio.run(consume_stream())
            except Exception as exc:
                output_queue.put(exc)
            finally:
                output_queue.put(stop_signal)

        worker = threading.Thread(target=run_async_stream, daemon=True)
        worker.start()

        for item in iter(output_queue.get, stop_signal):
            if isinstance(item, Exception):
                worker.join()
                raise item
            yield item

        worker.join()


if __name__ == "__main__":
    agent = TravelGraphAgent()
    for chunk in agent.execute_stream("帮我规划杭州两日游，喜欢自然风景和咖啡"):
        print(chunk, end="", flush=True)
