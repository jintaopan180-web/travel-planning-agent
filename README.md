# AI 旅游规划 Agent

这是一个基于 LangChain、LangGraph、Streamlit 和高德地图 MCP 的旅游规划智能助手。项目重点演示多节点 Agent 编排、结构化状态流转、工具调用兜底、Human-in-the-loop 缺信息追问，以及面向面试展示的 Agent 工程化设计。

## 项目亮点

- **LangGraph 多节点工作流**：使用 `StateGraph` 编排需求解析、天气、公交、打车和统筹规划节点。
- **Human-in-the-loop 追问机制**：当用户缺少城市或游玩天数时，条件边会路由到追问节点，而不是让模型继续猜。
- **城市内路线由 Agent 规划**：用户只需要提供城市、天数、想去的地点和偏好，景点顺序、日内起终点和交通衔接由 Agent 自动生成。
- **并行信息获取**：需求完整后，天气、公交、打车节点并行执行，再交给 planner 汇总。
- **结构化输出校验**：使用 Pydantic 和 JSON 提取处理 LLM 输出波动，解析失败时进入降级流程。
- **MCP 工具兜底**：优先调用高德 MCP；工具失败时尝试高德 REST API；仍失败则返回 mock 降级结果，保证工作流不中断。
- **可观测性基础**：通过 `errors`、`node_trace` 和工具调用日志记录节点流转、异常和 fallback 信息。

## 技术栈

- Python
- Streamlit
- LangChain
- LangGraph
- LangChain MCP Adapters
- Pydantic
- DashScope / 通义千问 Qwen
- 高德地图 MCP / REST API

## 项目结构

```text
.
├── app.py                       # Streamlit 前端入口
├── agent/
│   ├── travel_graph.py          # LangGraph 工作流与条件边
│   ├── state.py                 # TravelState 全局状态
│   ├── schemas.py               # Pydantic 结构化模型
│   ├── react_agent.py           # 兼容旧入口的 Agent 封装
│   ├── nodes/
│   │   ├── common.py            # 节点 Agent 构建与安全执行
│   │   ├── weather_node.py      # 天气节点
│   │   ├── transit_node.py      # 公交节点
│   │   ├── taxi_node.py         # 打车节点
│   │   └── planner_node.py      # 统筹规划节点
│   └── tools/
│       ├── agent_tools.py       # 高德 MCP 工具加载
│       ├── middleware.py        # 工具调用日志与异常捕获
│       └── fallbacks.py         # MCP -> REST API -> Mock 兜底
├── config/
│   └── agent.example.yml        # 配置模板，不包含真实密钥
├── model/
│   └── factory.py               # 聊天模型初始化
├── prompts/
│   └── main_prompt.txt          # 主提示词参考
├── utils/
│   ├── config_handler.py        # YAML 配置读取
│   ├── logger_handler.py        # 日志配置
│   └── path_tool.py             # 路径工具
├── requirements.txt
└── README.md
```

## 工作流

```text
用户输入
  -> parse_requirements 结构化解析需求
  -> 条件边判断是否缺少城市/天数
      -> 缺信息：ask_user_node 追问用户
      -> 信息足够：weather / transit / taxi 并行执行
  -> planner 汇总天气、公交、打车结果
  -> 输出最终旅行计划
```

## 安装

建议使用 Python 3.10 或以上版本。

```bash
pip install -r requirements.txt
```

## 配置密钥

不要把真实 API Key 提交到 GitHub。推荐使用环境变量：

Windows PowerShell：

```powershell
$env:DASHSCOPE_API_KEY="your-dashscope-api-key"
$env:AMAP_MCP_URL="https://mcp.amap.com/mcp?key=your-amap-key"
$env:AMAP_API_KEY="your-amap-key"
$env:CHAT_MODEL_NAME="qwen3.7-max"
```

也可以复制配置模板到本地：

```powershell
Copy-Item config/agent.example.yml config/agent.yml
```

然后在 `config/agent.yml` 中填写本地密钥。该文件已被 `.gitignore` 忽略，不应上传。

## 启动

```bash
streamlit run app.py
```

浏览器打开：

```text
http://127.0.0.1:8501
```

## 测试示例

触发 HITL 追问：

```text
帮我规划一个旅行
```

```text
帮我规划杭州旅行，喜欢自然风景和咖啡
```

直接进入规划：

```text
帮我规划杭州两日游，想去西湖、灵隐寺、河坊街，喜欢咖啡和自然风景
```

用户补充信息示例：

```text
杭州，两天，想去西湖、灵隐寺和几家咖啡馆
```

## 安全说明

- `config/agent.yml`、`.env`、`.streamlit/secrets.toml` 等本地密钥文件不要提交。
- 如果真实 key 曾经进入 Git 历史，建议到对应平台重置 key。
- 本项目不支持真实预订、购票、支付或叫车下单，只用于规划建议和 Agent 工作流演示。

## 后续可扩展方向

- 增加 LangGraph checkpointer，实现状态持久化、恢复和调试回放。
- 增加 review/refine 节点，实现 Reflection / Self-Refinement。
- 增加长期记忆，保存用户常用出发地、预算、节奏和兴趣偏好。
- 接入更完整的城市/POI 识别，减少手写城市词表。
- 建立固定评估集，统计工具成功率、降级率、追问准确率和规划完整性。
