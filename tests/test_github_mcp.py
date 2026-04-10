"""GitHub MCP サーバーのユニットテスト."""

import pytest
from unittest.mock import patch, MagicMock

from src.mcp_servers.github_mcp_server import (
    list_repository_files,
    get_file_content,
    search_code,
    get_directory_structure,
)


class TestListRepositoryFiles:
    """list_repository_files ツールのテスト."""

    @patch("src.mcp_servers.github_mcp_server._github_get")
    def test_basic_listing(self, mock_get):
        mock_get.return_value = {
            "tree": [
                {"path": "README.md", "type": "blob", "size": 1024},
                {"path": "src/main.py", "type": "blob", "size": 2048},
                {"path": "src", "type": "tree"},
            ]
        }
        result = list_repository_files("owner", "repo")
        assert "2 ファイル" in result
        assert "README.md" in result
        assert "src/main.py" in result

    @patch("src.mcp_servers.github_mcp_server._github_get")
    def test_extension_filter(self, mock_get):
        mock_get.return_value = {
            "tree": [
                {"path": "README.md", "type": "blob", "size": 100},
                {"path": "main.py", "type": "blob", "size": 200},
                {"path": "test.js", "type": "blob", "size": 300},
            ]
        }
        result = list_repository_files("o", "r", extensions=".py")
        assert "main.py" in result
        assert "README.md" not in result

    @patch("src.mcp_servers.github_mcp_server._github_get")
    def test_path_filter(self, mock_get):
        mock_get.return_value = {
            "tree": [
                {"path": "src/a.py", "type": "blob", "size": 100},
                {"path": "docs/b.md", "type": "blob", "size": 200},
            ]
        }
        result = list_repository_files("o", "r", path="src")
        assert "a.py" in result
        assert "b.md" not in result


class TestGetFileContent:
    """get_file_content ツールのテスト."""

    @patch("src.mcp_servers.github_mcp_server._github_get")
    def test_base64_decode(self, mock_get):
        import base64
        content = "# Hello World\n\ndef main():\n    pass\n"
        mock_get.return_value = {
            "encoding": "base64",
            "content": base64.b64encode(content.encode()).decode(),
        }
        result = get_file_content("o", "r", "main.py")
        assert "Hello World" in result
        assert "def main" in result

    @patch("src.mcp_servers.github_mcp_server._github_get")
    def test_no_content(self, mock_get):
        mock_get.return_value = {"encoding": "none", "content": None}
        result = get_file_content("o", "r", "binary.bin")
        assert "取得できません" in result


class TestSearchCode:
    """search_code ツールのテスト."""

    @patch("src.mcp_servers.github_mcp_server._github_get")
    def test_basic_search(self, mock_get):
        mock_get.return_value = {
            "total_count": 5,
            "items": [
                {"repository": {"full_name": "org/repo"}, "path": "auth.py", "score": 1.0},
            ],
        }
        result = search_code("authenticate")
        assert "5 件" in result
        assert "auth.py" in result

    @patch("src.mcp_servers.github_mcp_server._github_get")
    def test_no_results(self, mock_get):
        mock_get.return_value = {"total_count": 0, "items": []}
        result = search_code("nonexistent_function_xyz")
        assert "見つかりません" in result
