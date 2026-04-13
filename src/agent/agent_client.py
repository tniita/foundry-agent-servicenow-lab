"""Foundry Agent Service クライアント — Prompt Agent + Responses API.

Foundry IQ KB (MCPTool) と GitHub (MCPTool) を統合し、
ユーザーからのシステム問い合わせに自動応答する。

両ツールともサーバーサイド MCPTool のためクライアント側の dispatch は不要。
エージェントは setup_agent.py で事前に作成しておく必要がある。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from src.config import project_cfg

logger = logging.getLogger(__name__)


def _create_project_client() -> AIProjectClient:
    """AIProjectClient を初期化する."""
    return AIProjectClient(
        endpoint=project_cfg.endpoint,
        credential=DefaultAzureCredential(),
    )


def chat(
    user_message: str,
    conversation_id: Optional[str] = None,
) -> dict[str, Any]:
    """ユーザーメッセージに対して Foundry Agent Service 経由で回答を生成する.

    KB と GitHub の両ツールはサーバーサイド MCPTool として自動実行されるため、
    クライアント側での dispatch ループは不要。

    Args:
        user_message: ユーザーの質問テキスト
        conversation_id: 既存の会話 ID（マルチターン時）

    Returns:
        dict: answer, conversation_id, timing を含む辞書
    """
    if not user_message or not user_message.strip():
        raise ValueError("メッセージが空です。")

    t_start = time.perf_counter()
    project_client = _create_project_client()
    openai_client = project_client.get_openai_client()

    # 会話セッション (新規 or 既存)
    if conversation_id is None:
        conversation = openai_client.conversations.create()
        conversation_id = conversation.id

    # エージェント参照でリクエストを送信
    # KB MCPTool / GitHub MCPTool ともサーバーサイドで自動実行される
    response = openai_client.responses.create(
        input=user_message,
        conversation=conversation_id,
        extra_body={
            "agent_reference": {
                "name": project_cfg.agent_name,
                "type": "agent_reference",
            }
        },
    )

    # 最終テキスト回答を抽出
    answer = response.output_text if hasattr(response, "output_text") else ""
    if not answer:
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if hasattr(content, "text"):
                        answer += content.text

    t_total = time.perf_counter() - t_start

    return {
        "answer": answer,
        "conversation_id": conversation_id,
        "timing": {"total": t_total},
    }
