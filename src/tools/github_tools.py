"""GitHub API ユーティリティ — 参考コード.

GitHub リモート MCP サーバーへの移行により、これらの関数は
直接使用されなくなりました。Agent Service の MCPTool がサーバーサイドで
GitHub MCP を自動実行します。テストやデバッグ用の参考コードとして残しています。
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import requests

from src.config import github_cfg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------
def _headers() -> dict[str, str]:
    """GitHub API 用ヘッダーを構築する."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_cfg.token:
        headers["Authorization"] = f"Bearer {github_cfg.token}"
    return headers


def _get(url: str, params: dict | None = None) -> dict[str, Any]:
    """GitHub API への GET リクエストを発行する."""
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# ツール定義 (OpenAI function schema) — 参考用
# ---------------------------------------------------------------------------
GITHUB_FUNCTION_TOOLS = [
    {
        "type": "function",
        "name": "search_code",
        "description": (
            "GitHub リポジトリのソースコードをキーワード検索する。"
            "関数名、クラス名、エラーメッセージなどのコード検索に使用する。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "コード検索キーワード（関数名、クラス名、エラーメッセージなど）",
                },
                "language": {
                    "type": "string",
                    "description": "プログラミング言語フィルタ（python, csharp, typescript 等）",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "get_file_content",
        "description": (
            "GitHub リポジトリ内の特定のファイルの内容を取得する。"
            "設計書（.md）やソースコードの詳細確認に使用する。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "取得したいファイルのパス（例: docs/design.md, src/main.py）",
                },
            },
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "list_repository_files",
        "description": (
            "GitHub リポジトリのファイル一覧を取得する。"
            "リポジトリ構造の把握やファイル探索に使用する。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "対象ディレクトリのパス（空文字でルート）",
                },
                "extensions": {
                    "type": "string",
                    "description": "拡張子フィルタ（カンマ区切り。例: .py,.md）",
                },
            },
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# ツール実行関数
# ---------------------------------------------------------------------------
def search_code(query: str, language: str = "") -> str:
    """GitHub Code Search API でコードを検索する."""
    q_parts = [query]
    if github_cfg.owner and github_cfg.repo:
        q_parts.append(f"repo:{github_cfg.owner}/{github_cfg.repo}")
    if language:
        q_parts.append(f"language:{language}")

    data = _get(
        "https://api.github.com/search/code",
        {"q": " ".join(q_parts), "per_page": 20},
    )
    items = data.get("items", [])
    if not items:
        return f"コード検索結果なし: '{query}'"

    lines = [f"検索結果: {data.get('total_count', 0)} 件\n"]
    for item in items:
        repo_name = item.get("repository", {}).get("full_name", "")
        lines.append(f"- {repo_name}/{item.get('path', '')}")
    return "\n".join(lines)


def get_file_content(path: str) -> str:
    """GitHub Contents API でファイル内容を取得する."""
    owner = github_cfg.owner
    repo = github_cfg.repo
    ref = github_cfg.branch

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
    try:
        data = _get(url)
    except requests.HTTPError as e:
        return f"ファイル取得失敗: {path} ({e})"

    if data.get("encoding") == "base64" and data.get("content"):
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        if len(content) > 8000:
            content = content[:8000] + f"\n\n... (以降省略。全体 {len(content)} 文字)"
        return f"📄 {owner}/{repo}/{path}\n{'=' * 40}\n{content}"
    return f"内容を取得できません: {path}"


def list_repository_files(path: str = "", extensions: str = "") -> str:
    """GitHub Trees API でファイル一覧を取得する."""
    owner = github_cfg.owner
    repo = github_cfg.repo
    ref = github_cfg.branch

    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
    tree = _get(url).get("tree", [])

    files = [item for item in tree if item["type"] == "blob"]
    if path:
        prefix = path.rstrip("/") + "/"
        files = [f for f in files if f["path"].startswith(prefix)]
    if extensions:
        ext_set = {e.strip() for e in extensions.split(",") if e.strip()}
        files = [f for f in files if any(f["path"].endswith(ext) for ext in ext_set)]

    if not files:
        return f"ファイルが見つかりません: {owner}/{repo}/{path}"
    lines = [f"📁 {owner}/{repo} — {len(files)} ファイル\n"]
    for f in files[:80]:
        lines.append(f"  {f['path']}")
    if len(files) > 80:
        lines.append(f"  ... 他 {len(files) - 80} ファイル")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ディスパッチャ
# ---------------------------------------------------------------------------
def dispatch(name: str, arguments: dict[str, Any]) -> str:
    """ツール名に応じて実行し結果を返す."""
    try:
        if name == "search_code":
            return search_code(
                query=arguments["query"],
                language=arguments.get("language", ""),
            )
        elif name == "get_file_content":
            return get_file_content(path=arguments["path"])
        elif name == "list_repository_files":
            return list_repository_files(
                path=arguments.get("path", ""),
                extensions=arguments.get("extensions", ""),
            )
        else:
            return f"未知のツール: {name}"
    except Exception as e:
        logger.error("GitHub ツール実行エラー (%s): %s", name, e)
        return f"ツール実行中にエラーが発生しました: {e}"
