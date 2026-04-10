"""Foundry IQ ナレッジベース検索サービスのユニットテスト."""

import pytest
from unittest.mock import patch, MagicMock

from src.foundry_iq.kb_query_service import (
    _extract_answer,
    _extract_citations,
    query_knowledge_base,
)


class TestExtractAnswer:
    """_extract_answer 関数のテスト."""

    def test_single_response(self):
        content_item = MagicMock()
        content_item.text = "テスト回答です。"
        response_item = MagicMock()
        response_item.content = [content_item]
        result = MagicMock()
        result.response = [response_item]

        answer = _extract_answer(result)
        assert "テスト回答" in answer

    def test_empty_response(self):
        result = MagicMock()
        result.response = []
        answer = _extract_answer(result)
        assert "回答を生成できませんでした" in answer

    def test_no_response_attr(self):
        result = MagicMock(spec=[])
        answer = _extract_answer(result)
        assert "回答を生成できませんでした" in answer


class TestExtractCitations:
    """_extract_citations 関数のテスト."""

    def test_search_index_citation(self):
        ref = MagicMock()
        ref.type = "searchIndex"
        ref.reranker_score = 0.95
        ref.source_data = {"title": "テストドキュメント", "content": "テスト内容"}
        ref.additional_properties = {"incident_number": "INC0001234", "file_path": None}

        result = MagicMock()
        result.references = [ref]

        citations = _extract_citations(result)
        assert len(citations) == 1
        assert citations[0]["type"] == "searchIndex"
        assert citations[0]["incident_number"] == "INC0001234"
        assert citations[0]["relevance_score"] == 0.95

    def test_no_references(self):
        result = MagicMock()
        result.references = None
        citations = _extract_citations(result)
        assert citations == []


class TestQueryKnowledgeBase:
    """query_knowledge_base 関数のテスト."""

    def test_empty_question_raises(self):
        with pytest.raises(ValueError, match="質問テキストが空"):
            query_knowledge_base("")

    def test_whitespace_question_raises(self):
        with pytest.raises(ValueError, match="質問テキストが空"):
            query_knowledge_base("   ")
