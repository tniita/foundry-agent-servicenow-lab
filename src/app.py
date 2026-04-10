"""Streamlit チャットアプリ — Foundry Agent Service 統合.

Foundry IQ KB (MCPTool) と GitHub Function Tools を統合した
Prompt Agent を通じて、システム問い合わせに自動応答する。

起動:
    streamlit run src/app.py
"""

from __future__ import annotations

import streamlit as st

from src.agent.agent_client import chat
from src.config import foundry_iq_cfg, github_cfg, project_cfg

# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="システム問い合わせ チャットボット",
    page_icon="🤖",
    layout="wide",
)

# ---------------------------------------------------------------------------
# サイドバー — 設定 & 情報
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 設定")

    st.subheader("📚 情報ソース")
    st.markdown(f"""
    | ソース | 接続先 |
    |--------|--------|
    | 🎫 インシデント | Foundry IQ KB: `{foundry_iq_cfg.knowledge_base_name}` |
    | 💻 コード/設計書 | GitHub: `{github_cfg.owner}/{github_cfg.repo}` |
    """)

    st.divider()
    st.subheader("🔧 アーキテクチャ")
    st.caption(
        f"Foundry Agent Service (`{project_cfg.agent_name}`) が\n"
        "ユーザーの質問を分析し、Foundry IQ KB (MCP) または\n"
        "GitHub Function Tools を自動選択して回答を生成します。"
    )

    st.divider()
    if st.button("🗑️ 会話をクリア"):
        st.session_state.messages = []
        st.session_state.conversation_id = None
        st.rerun()

# ---------------------------------------------------------------------------
# セッション状態の初期化
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

# ---------------------------------------------------------------------------
# チャット UI
# ---------------------------------------------------------------------------
st.title("🤖 システム問い合わせ チャットボット")
st.caption(
    "インシデント情報（Foundry IQ KB）+ ソースコード・設計書（GitHub）を統合検索します"
)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            with st.expander(f"🔧 ツール呼び出し ({len(msg['tool_calls'])} 回)", expanded=False):
                for tc in msg["tool_calls"]:
                    st.markdown(f"**{tc['tool']}**(`{tc['arguments']}`)")
                    st.text(tc.get("result_preview", "")[:300])
                    st.divider()

# ---------------------------------------------------------------------------
# ユーザー入力
# ---------------------------------------------------------------------------
if prompt := st.chat_input("システムについて質問してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("エージェントが検索・回答を生成中..."):
            try:
                result = chat(
                    user_message=prompt,
                    conversation_id=st.session_state.conversation_id,
                )

                answer = result["answer"]
                tool_calls = result.get("tool_calls", [])
                timing = result.get("timing", {})

                # 会話 ID を保持（マルチターン対応）
                st.session_state.conversation_id = result.get("conversation_id")

                st.markdown(answer)

                if tool_calls:
                    with st.expander(
                        f"🔧 ツール呼び出し ({len(tool_calls)} 回)", expanded=False
                    ):
                        for tc in tool_calls:
                            st.markdown(f"**{tc['tool']}**(`{tc['arguments']}`)")
                            st.text(tc.get("result_preview", "")[:300])
                            st.divider()

                st.caption(f"⏱️ 合計: {timing.get('total', 0):.2f}s")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "tool_calls": tool_calls,
                })

            except Exception as e:
                error_msg = f"エラーが発生しました: {e}"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg,
                })
