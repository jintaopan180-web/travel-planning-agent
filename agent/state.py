import operator
from typing import Annotated, Any, TypedDict


class TravelState(TypedDict, total=False):
    """
    旅行规划工作流的全局状态。

    第二步的目标是让节点之间通过结构化字段传递上下文，而不是只传字符串。
    第三步才会继续补充公交/打车经济性对比的具体计算逻辑。
    """

    # 用户需求相关字段，由入口和需求解析节点维护。
    user_query: str
    destination: str
    origin: str | None
    travel_days: int | None
    preferences: list[str]

    # 节点产物字段，由各业务节点写入，统筹节点统一读取。
    weather: dict[str, Any]
    transit_routes: list[dict[str, Any]]
    taxi_routes: list[dict[str, Any]]
    route_comparison: dict[str, Any]
    final_plan: str

    # 调试与容错字段，方便观察节点流转和记录后续异常降级信息。
    # 并行节点可能同时写 errors，用 reducer 合并，避免分支并发更新冲突。
    errors: Annotated[list[str], operator.add]
    # 并行节点都会写 node_trace，用 reducer 把多个分支返回的列表拼接起来。
    node_trace: Annotated[list[str], operator.add]
    raw: dict[str, Any]


# 兼容第一步代码中使用过的旧类型名，后续可以统一改成 TravelState。
TravelGraphState = TravelState
