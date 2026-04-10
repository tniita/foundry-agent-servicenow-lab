"""Foundry Agent Service クライアント — Prompt Agent + Responses API.

Foundry IQ KB (MCPTool 経由) と GitHub Function Tools を統合し、
ユーザーからのシステム問い合わせに自動応答する。

エージェントは setup_agent.py で事前に作成しておく必要がある。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from src.config import project_cfg
from src.tools.github_tools import GITHUB_FUNCTION_TOOLS, dispatch as dispatch_github

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
    max_tool_rounds: int = 5,
) -> dict[str, Any]:
    """ユーザーメッセージに対して Foundry Agent Service 経由で回答を生成する.

    Args:
        user_message: ユーザーの質問テキスト
        conversation_id: 既存の会話 ID（マルチターン時）
        max_tool_rounds: Function Tool 呼び出しの最大ラウンド数

    Returns:
        dict: answer, conversation_id, tool_calls, timing を含む辞書
    """
    if not user_message or not user_message.strip():
        raise ValueError("メッセージが空です。")

    t_start = time.perf_counter()
    tool_call_log: list[dict[str, Any]] = []

    project_client = _create_project_client()
    openai_client = project_client.get_openai_client()

    # 会話セッション (新規 or 既存)
    if conversation_id is None:
        conversation = openai_client.conversations.create()
        conversation_id = conversation.id

    # エージェント参照でリクエストを送信
    # MCPTool (Foundry IQ KB) はエージェント側で自動実行される
    # GitHub Function Tools はクライアント側で実行が必要
    response = openai_client.responses.create(
        input=user_message,
        tools=GITHUB_FUNCTION_TOOLS,
        conversation=conversation_id,
        extra_body={
            "agent_reference": {
                "name": project_cfg.agent_name,
                "type": "agent_reference",
            }
        },
    )

    # Function Tool 実行ループ
    for _round in range(max_tool_rounds):
        # Function Call アイテムを抽出
        function_calls = [
            item for item in response.output
            if item.type == "function_call"
        ]

        if not function_calls:
            break

        # Function を実行して結果を構築
        tool_results = []
        for fc in function_calls:
            fn_name = fc.name
            fn_args = json.loads(fc.arguments) if isinstance(fc.arguments, str) else fc.arguments
            logger.info("Function Tool 呼び出し: %s(%s)", fn_name, fn_args)

            result_str = dispatch_github(fn_name, fn_args)
            tool_call_log.append({
                "tool": fn_name,
                "arguments": fn_args,
                "result_preview": result_str[:200],
            })

            tool_results.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": result_str,
            })

        # ツール結果を送り返して次のレスポンスを取得
        response = openai_client.responses.create(
            input=tool_results,
            tools=GITHUB_FUNCTION_TOOLS,
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
        # output から message アイテムを探す
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if hasattr(content, "text"):
                        answer += content.text

    t_total = time.perf_counter() - t_start

    return {
        "answer": answer,
        "conversation_id": conversation_id,
        "tool_calls": tool_call_log,
        "timing": {"total": t_total},
    }
