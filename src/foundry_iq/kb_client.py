"""Foundry IQ KnowledgeBaseRetrievalClient のラッパー.

Azure AI Search 上に作成した Foundry IQ ナレッジベースに対して
アジェンティック検索を実行するクライアントを提供する。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient

from src.config import foundry_iq_cfg


class KBClientError(RuntimeError):
    """ナレッジベースクライアントの設定エラー."""


def _validate_config() -> None:
    """必須設定値の存在を検証する."""
    if not foundry_iq_cfg.search_endpoint:
        raise KBClientError("AZURE_SEARCH_ENDPOINT が設定されていません。")
    if not foundry_iq_cfg.search_api_key:
        raise KBClientError("AZURE_SEARCH_API_KEY が設定されていません。")
    if not foundry_iq_cfg.knowledge_base_name:
        raise KBClientError("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME が設定されていません。")


@lru_cache(maxsize=1)
def get_kb_client() -> KnowledgeBaseRetrievalClient:
    """シングルトンの KnowledgeBaseRetrievalClient を返す."""
    _validate_config()
    return KnowledgeBaseRetrievalClient(
        endpoint=foundry_iq_cfg.search_endpoint,
        knowledge_base_name=foundry_iq_cfg.knowledge_base_name,
        credential=AzureKeyCredential(foundry_iq_cfg.search_api_key),
    )


def get_kb_info() -> dict:
    """UI 表示用のナレッジベース情報を返す."""
    return {
        "endpoint": foundry_iq_cfg.search_endpoint,
        "knowledge_base_name": foundry_iq_cfg.knowledge_base_name,
        "knowledge_source_name": foundry_iq_cfg.knowledge_source_name,
    }
