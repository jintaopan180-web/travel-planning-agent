from agent.travel_graph import TravelGraphAgent


class ReactAgent(TravelGraphAgent):
    """
    兼容旧入口的旅行规划 Agent。

    第一阶段已经把单体 ReAct 流程切换为显式 StateGraph 工作流。
    app.py 仍然可以继续 import ReactAgent，不需要同步修改前端入口。
    """

    pass


if __name__ == "__main__":
    agent = ReactAgent()

    for chunk in agent.execute_stream("Plan a two-day trip to Hangzhou with nature views and cafes."):
        print(chunk, end="", flush=True)
