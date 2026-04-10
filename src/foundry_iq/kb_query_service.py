"""Foundry IQ ナレッジベース検索サービス.

UI レイヤーとコンソールの両方から利用できる共通の検索ロジックを提供する。
KnowledgeBaseRetrievalClient のアジェンティック検索を使い、
質問分解→マルチソース検索→回答合成を Foundry IQ に委譲する。
"""

from __future__ import annotations

import time
from typing import Any, Optional

from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalLowReasoningEffort,
    KnowledgeRetrievalMediumReasoningEffort,
    KnowledgeRetrievalMinimalReasoningEffort,
)

from src.config import foundry_iq_cfg
from src.foundry_iq.kb_client import get_kb_client

# ---------------------------------------------------------------------------
# 推論努力レベルマッピング
# ---------------------------------------------------------------------------
_REASONING_FACTORIES = {
    "minimal": KnowledgeRetrievalMinimalReasoningEffort,
    "low": KnowledgeRetrievalLowReasoningEffort,
    "medium": KnowledgeRetrievalMediumReasoningEffort,
}


# ---------------------------------------------------------------------------
# リクエスト構築
# ---------------------------------------------------------------------------
def _build_request(
    question: str,
    reasoning_effort: Optional[str] = None,
    conversation_history: Optional[list[dict[str, str]]] = None,
) -> KnowledgeBaseRetrievalRequest:
    """Foundry IQ 検索リクエストを構築する.

    Blob Knowledge Source を使用する場合、ナレッジソースの指定は
    Knowledge Base 定義に含まれるため source_params は不要。
    """

    # メッセージ履歴の構築（会話コンテキストの維持）
    messages = []
    if conversation_history:
        for msg in conversation_history[-5:]:  # 直近5ターンまで
            messages.append(
                KnowledgeBaseMessage(
                    role=msg["role"],
                    content=[KnowledgeBaseMessageTextContent(text=msg["content"])],
                )
            )

    messages.append(
        KnowledgeBaseMessage(
            role="user",
            content=[KnowledgeBaseMessageTextContent(text=question.strip())],
        )
    )

    request_kwargs: dict[str, Any] = {
        "messages": messages,
        "include_activity": True,
    }

    # 推論努力レベル
    if reasoning_effort and reasoning_effort.lower() in _REASONING_FACTORIES:
        request_kwargs["retrieval_reasoning_effort"] = _REASONING_FACTORIES[
            reasoning_effort.lower()
        ]()

    return KnowledgeBaseRetrievalRequest(**request_kwargs)


# ---------------------------------------------------------------------------
# レスポンス解析
# ---------------------------------------------------------------------------
def _extract_answer(result: Any) -> str:
    """レスポンスからテキスト回答を抽出する."""
    texts: list[str] = []
    if getattr(result, "response", None):
        for response_item in result.response:
            if getattr(response_item, "content", None):
                for content_item in response_item.content:
                    text_value = getattr(content_item, "text", None)
                    if text_value:
                        texts.append(text_value.strip())
    return "\n\n".join(texts) if texts else "回答を生成できませんでした。"


def _extract_citations(result: Any) -> list[dict[str, Any]]:
    """レスポンスから引用情報を抽出する."""
    citations: list[dict[str, Any]] = []
    references = getattr(result, "references", None)
    if not references:
        return citations

    for idx, ref in enumerate(references):
        source_type = getattr(ref, "type", "unknown")
        source_data = getattr(ref, "source_data", None)
        additional_props = getattr(ref, "additional_properties", None)

        citation: dict[str, Any] = {
            "id": idx,
            "type": source_type,
            "title": None,
            "content_snippet": None,
            "relevance_score": getattr(ref, "reranker_score", None),
        }

        if source_type == "searchIndex":
            if isinstance(source_data, dict):
                citation["title"] = source_data.get("title", "")
                citation["content_snippet"] = source_data.get("content", "")[:300]
            if isinstance(additional_props, dict):
                citation["title"] = citation["title"] or additional_props.get("title", "")
                # インシデント番号やファイルパスなど追加メタデータ
                citation["incident_number"] = additional_props.get("incident_number")
                citation["file_path"] = additional_props.get("file_path")

        citations.append(citation)

    return citations


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------
def query_knowledge_base(
    question: str,
    reasoning_effort: str = "medium",
    conversation_history: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """Foundry IQ ナレッジベースに質問を投げ、構造化された結果を返す.

    Args:
        question: ユーザーの質問テキスト
        reasoning_effort: 推論努力レベル (minimal / low / medium)
        conversation_history: 会話履歴 [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        dict: answer, citations, timing, activity を含む辞書
    """
    if not question or not question.strip():
        raise ValueError("質問テキストが空です。")

    # リクエスト構築
    t0 = time.perf_counter()
    request = _build_request(question, reasoning_effort, conversation_history)
    t_build = time.perf_counter() - t0

    # アジェンティック検索実行
    t1 = time.perf_counter()
    client = get_kb_client()
    result = client.retrieve(request)
    t_retrieve = time.perf_counter() - t1

    # レスポンス解析
    t2 = time.perf_counter()
    answer = _extract_answer(result)
    citations = _extract_citations(result)
    t_process = time.perf_counter() - t2

    return {
        "question": question.strip(),
        "answer": answer,
        "citations": citations,
        "timing": {
            "total": t_build + t_retrieve + t_process,
            "request_build": t_build,
            "kb_retrieval": t_retrieve,
            "response_processing": t_process,
        },
        "metadata": {
            "knowledge_base": foundry_iq_cfg.knowledge_base_name,
            "reasoning_effort": reasoning_effort,
        },
        "activity": getattr(result, "activity", None),
    }
