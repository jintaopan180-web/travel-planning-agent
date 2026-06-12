import streamlit as st

from agent.react_agent import ReactAgent


st.set_page_config(page_title="旅游规划智能助手")
st.title("旅游规划智能助手")
st.divider()

if "message" not in st.session_state:
    st.session_state["message"] = []

if "agent" not in st.session_state:
    st.session_state["agent"] = None

for message in st.session_state["message"]:
    st.chat_message(message["role"]).write(message["content"])

prompt = st.chat_input("例如：帮我规划杭州两日游，喜欢自然风景和咖啡")

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role": "user", "content": prompt})

    try:
        if st.session_state["agent"] is None:
            with st.spinner("正在初始化旅游规划 Agent..."):
                st.session_state["agent"] = ReactAgent()

        with st.spinner("正在规划行程..."):
            res_stream = st.session_state["agent"].execute_stream(prompt)
            with st.chat_message("assistant"):
                full_response = st.write_stream(res_stream)

        if isinstance(full_response, str):
            assistant_message = full_response.strip()
        elif isinstance(full_response, list):
            assistant_message = "".join(str(item) for item in full_response).strip()
        else:
            assistant_message = str(full_response).strip()

        if not assistant_message:
            assistant_message = "当前没有生成有效回复，请检查模型配置或高德 MCP 工具加载状态。"
            st.chat_message("assistant").write(assistant_message)

        st.session_state["message"].append(
            {"role": "assistant", "content": assistant_message}
        )

    except Exception as exc:
        error_message = f"运行出错：{exc}"
        st.chat_message("assistant").write(error_message)
        st.session_state["message"].append(
            {"role": "assistant", "content": error_message}
        )
