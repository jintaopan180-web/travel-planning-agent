# AI 旅游规划 ReAct Agent 智能助手

基于 LangChain、LangGraph 和高德地图 MCP 的本地旅游规划智能助手。项目将旅游规划拆分为需求解析、天气查询、公交路线规划、打车方案生成和统筹规划等节点，通过 LangGraph StateGraph 编排多节点并行工作流，并使用 Streamlit 提供流式对话界面。

## 功能特性

- 多节点工作流编排：使用 LangGraph StateGraph 将天气、公交、打车和统筹规划拆分为单职责节点。
- 并行信息获取：需求解析后并行执行天气、公交和打车节点，再由 planner 节点统一汇总。
- 高德 MCP 工具接入：动态加载高德地图 MCP 工具，支持天气、POI、地理编码、路线规划、距离测量等能力。
- 结构化状态流转：通过 TravelState 管理用户需求、天气结果、公交路线、打车方案、错误信息和最终输出。
- 结构化解析与降级：使用 JSON 提取和 Pydantic 校验处理 LLM 输出格式波动。
- 工具兜底链路：MCP 调用失败后尝试高德 REST API，再失败则返回 Mock 静态结果，保证流程不中断。
- Streamlit 对话界面：支持用户输入旅游需求并流式返回规划结果。

## 技术栈

- LangChain
- LangGraph
- LangChain MCP Adapters
- 高德地图 MCP
- 通义千问 Qwen / DashScope
- Pydantic
- Streamlit

## 项目结构

```text
.
├── agent/
│   ├── travel_graph.py          # LangGraph 工作流入口
│   ├── state.py                 # TravelState 全局状态
│   ├── schemas.py               # Pydantic 结构化模型和 JSON 后处理
│   ├── react_agent.py           # 兼容旧入口的 Agent 封装
│   ├── nodes/
│   │   ├── weather_node.py      # 天气查询节点
│   │   ├── transit_node.py      # 公交路线节点
│   │   ├── taxi_node.py         # 打车方案节点
│   │   ├── planner_node.py      # 统筹规划节点
│   │   └── common.py            # 节点 Agent 构建与安全执行
│   └── tools/
│       ├── agent_tools.py       # 高德 MCP 工具加载
│       ├── middleware.py        # 工具调用日志与异常处理
│       └── fallbacks.py         # MCP -> REST API -> Mock 兜底
├── config/
│   └── agent.example.yml        # 本地配置示例
├── model/
│   └── factory.py               # Qwen 聊天模型初始化
├── prompts/
│   └── main_prompt.txt          # 旅游规划主提示词参考
├── utils/
│   ├── config_handler.py        # YAML 配置加载
│   ├── logger_handler.py        # 日志配置
│   └── path_tool.py             # 路径工具
├── app.py                       # Streamlit 应用入口
├── requirements.txt
└── README.md
```

## 环境要求

- Python 3.10 或以上
- DashScope API Key
- 高德地图 MCP URL 或高德 API Key

## 安装

```bash
pip install -r requirements.txt
```

## 配置

复制示例配置文件：

```bash
cp config/agent.example.yml config/agent.yml
```

Windows PowerShell：

```powershell
Copy-Item config/agent.example.yml config/agent.yml
```

推荐使用环境变量配置密钥，避免把真实 key 写入仓库。

Windows PowerShell：

```powershell
$env:DASHSCOPE_API_KEY="your-dashscope-api-key"
$env:AMAP_MCP_URL="https://mcp.amap.com/mcp?key=your-amap-key"
$env:AMAP_API_KEY="your-amap-key"
```

Linux/macOS：

```bash
export DASHSCOPE_API_KEY="your-dashscope-api-key"
export AMAP_MCP_URL="https://mcp.amap.com/mcp?key=your-amap-key"
export AMAP_API_KEY="your-amap-key"
```

可选模型名：

```bash
export CHAT_MODEL_NAME="qwen3-max"
```

`config/agent.yml` 已被 `.gitignore` 忽略，请不要提交包含真实 key 的本地配置文件。

## 启动

```bash
streamlit run app.py
```

示例输入：

```text
帮我规划杭州两日游，喜欢自然风景和咖啡
```

## 工作流

```text
用户输入
  -> parse_requirements
  -> weather / transit / taxi 并行执行
  -> planner 汇总
  -> 最终行程输出
```

## 安全说明

- 不要提交真实的 `DASHSCOPE_API_KEY`、`AMAP_MCP_URL`、`AMAP_API_KEY`。
- 不要提交 `config/agent.yml`、`.env`、`.streamlit/secrets.toml`、`logs/`、`chroma_db/`。
- 如果真实 key 曾经提交到公开仓库，请立即在对应平台作废并重新生成。

## 当前边界

本项目主要用于学习和演示 Agent 工作流、MCP 工具调用和旅游规划文本生成，不支持真实预订、支付、购票或叫车下单。地图和交通信息可能受工具返回结果影响，实际出行前请再次核对实时信息。
