import asyncio
import threading
from queue import Queue
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes import planner_node, taxi_node, transit_node, weather_node
from agent.nodes.common import append_trace
from agent.state import TravelState


def parse_requirements_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    需求解析节点：初始化 TravelState 的需求相关字段。

    本步骤只建立全局状态结构，不做复杂的 LLM/Pydantic 解析；
    更细的目的地、天数、偏好抽取留到后续结构化解析步骤。
    """
    user_query = state.get("user_query", "").strip()
    return {
        "destination": state.get("destination", ""),
        "origin": state.get("origin"),
        "travel_days": state.get("travel_days"),
        "preferences": state.get("preferences", []),
        "node_trace": append_trace(state, "parse_requirements_node"),
    }


def build_travel_graph():
    """搭建并行 StateGraph：解析后并行查询天气、公交和打车，再汇总规划。"""
    graph = StateGraph(TravelState)

    graph.add_node("parse_requirements", parse_requirements_node)
    graph.add_node("weather", weather_node)
    graph.add_node("transit", transit_node)
    graph.add_node("taxi", taxi_node)
    graph.add_node("planner", planner_node)

    graph.add_edge(START, "parse_requirements")

    # parse_requirements 完成后，三个信息获取节点互不依赖，可以并行执行。
    graph.add_edge("parse_requirements", "weather")
    graph.add_edge("parse_requirements", "transit")
    graph.add_edge("parse_requirements", "taxi")

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
            "preferences": [],
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
