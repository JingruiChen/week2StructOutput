import json
import os
import pandas as pd
import streamlit as st
from pydantic import ValidationError

from new_chat_cli import generate_testcase, load_history, save_history, validate_and_save

TESTCASES_FILE = "new_testcases.json"

st.set_page_config(page_title="角色测试用例生成器", page_icon="🎮", layout="wide")


def login_page():
    st.title("🔐 登录")
    col, _ = st.columns([1, 2])
    with col:
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        if st.button("登录", type="primary", use_container_width=True):
            users = st.secrets.get("users", {})
            if username in users and users[username] == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("用户名或密码错误")
    st.stop()


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_page()

# ── 已登录 ──────────────────────────────────────────────────
col_title, col_logout = st.columns([6, 1])
with col_title:
    st.title("🎮 角色测试用例生成器")
with col_logout:
    st.markdown(f"<br>👤 {st.session_state.get('username', '')}", unsafe_allow_html=True)
    if st.button("退出登录"):
        st.session_state.logged_in = False
        st.rerun()

if "history" not in st.session_state:
    st.session_state.history = load_history()

# ── 调试面板（确认 Secrets 是否加载成功）───────────────────────
with st.expander("🔧 调试信息（确认 API Key 状态）", expanded=False):
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    base_url = st.secrets.get("ANTHROPIC_BASE_URL", "")
    st.write("ANTHROPIC_API_KEY:", f"{'✅ 已加载（前8位：' + api_key[:8] + '...）' if api_key else '❌ 未找到'}")
    st.write("ANTHROPIC_BASE_URL:", base_url if base_url else "❌ 未找到（将使用默认值）")

tab1, tab2, tab3 = st.tabs(["单条生成", "批量导入", "查看用例"])

# ── Tab 1: 单条生成 ──────────────────────────────────────────
with tab1:
    st.subheader("自然语言 → 测试用例")

    description = st.text_area(
        "输入角色描述",
        placeholder="例：代号白墨，真名陈若白，欧泊阵营，决斗定位。最大血量180，当前血量150。被动「墨痕」，战术「破锋斩」，终极「黑域斩灭」。",
        height=120,
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        generate_btn = st.button("生成用例", type="primary", use_container_width=True)
    with col2:
        if st.button("清除历史", use_container_width=False):
            st.session_state.history = []
            save_history([])
            st.success("历史已清除")

    if generate_btn:
        if not description.strip():
            st.warning("请输入角色描述")
        else:
            with st.spinner("正在生成..."):
                try:
                    result = generate_testcase(description, st.session_state.history)
                except Exception as e:
                    st.error(f"调用模型失败：{e}")
                    result = None

            if result is None:
                st.error("解析失败：输入信息不完整或无效，请补充角色描述后重试。")
                st.session_state.history.append({"role": "user", "content": description})
                st.session_state.history.append({"role": "assistant", "content": '{"error": "parse_failed"}'})
                save_history(st.session_state.history)
            else:
                try:
                    character = validate_and_save(result)
                    dumped = character.model_dump()
                    st.session_state.history.append({"role": "user", "content": description})
                    st.session_state.history.append({"role": "assistant", "content": json.dumps(dumped, ensure_ascii=False)})
                    save_history(st.session_state.history)
                    st.success("✅ 生成成功（Pydantic 校验通过）")
                    st.json(dumped)
                except ValidationError as e:
                    st.session_state.history.append({"role": "user", "content": description})
                    st.session_state.history.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})
                    save_history(st.session_state.history)
                    st.error(f"❌ Pydantic 校验失败：{e}")
                    st.json(result)

    if st.session_state.history:
        with st.expander(f"对话历史（{len(st.session_state.history) // 2} 轮）", expanded=False):
            for msg in st.session_state.history:
                role_label = "你" if msg["role"] == "user" else "Claude"
                st.markdown(f"**[{role_label}]** {msg['content']}")

# ── Tab 2: 批量导入 ──────────────────────────────────────────
with tab2:
    st.subheader("批量导入 Excel / CSV")
    st.markdown("文件需包含名为 **`角色描述`** 的列，每行一条自然语言描述。")

    uploaded = st.file_uploader("上传文件", type=["xlsx", "csv"])

    if uploaded:
        try:
            if uploaded.name.endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                df = pd.read_excel(uploaded)

            if "角色描述" not in df.columns:
                st.error(f"未找到「角色描述」列，当前列名：{list(df.columns)}")
            else:
                st.info(f"共检测到 {len(df)} 条描述")
                st.dataframe(df[["角色描述"]].head(5), use_container_width=True)

                if st.button("开始批量生成", type="primary"):
                    descriptions = df["角色描述"].dropna().tolist()
                    total = len(descriptions)
                    success, fail = 0, 0

                    progress = st.progress(0, text="准备中...")
                    result_container = st.container()

                    for i, desc in enumerate(descriptions, 1):
                        progress.progress(i / total, text=f"处理第 {i}/{total} 条...")
                        with result_container:
                            result = generate_testcase(str(desc), [])
                            if result is None:
                                fail += 1
                                st.error(f"第 {i} 条：❌ 解析失败 — {str(desc)[:40]}...")
                            else:
                                try:
                                    character = validate_and_save(result)
                                    success += 1
                                    st.success(f"第 {i} 条：✅ {character.code_name}（{character.faction} · {character.role}）")
                                except ValidationError as e:
                                    fail += 1
                                    st.warning(f"第 {i} 条：⚠️ 校验失败 — {e.errors()[0]['msg']}")

                    progress.empty()
                    st.markdown("---")
                    st.markdown(f"### 完成！成功 **{success}** 条 / 失败 **{fail}** 条")

        except Exception as e:
            st.error(f"文件读取失败：{e}")

# ── Tab 3: 查看用例 ──────────────────────────────────────────
with tab3:
    st.subheader("已保存的测试用例")

    col1, col2 = st.columns([1, 5])
    with col1:
        st.button("刷新", use_container_width=True)

    data = []
    if os.path.exists(TESTCASES_FILE):
        try:
            with open(TESTCASES_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []

    if not data:
        st.info("暂无测试用例，请先在「单条生成」或「批量导入」中生成。")
    else:
        df = pd.DataFrame(data)
        df.index = df.index + 1
        df.index.name = "序号"
        column_order = ["code_name", "real_name", "faction", "role", "max_hp", "current_hp", "passive", "tactical", "ultimate"]
        st.dataframe(df[column_order], use_container_width=True)
        st.markdown(f"共 **{len(data)}** 条用例")

        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        with col2:
            st.download_button(
                label="下载 JSON",
                data=json_str.encode("utf-8"),
                file_name="testcases.json",
                mime="application/json",
            )
