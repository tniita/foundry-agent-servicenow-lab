# Module 2: GitHub Function Tools 構築

## 学習目標

- Foundry Agent Service の Function Tools の仕組みを理解する
- GitHub リポジトリにアクセスする Function Tools を実装する
- ツールスキーマの定義とディスパッチロジックを理解する

## 概要

従来のアプローチでは GitHub のソースコードを事前にインデックスに取り込むか、
MCP サーバーとして独立プロセスで公開していましたが、本ラボでは **Foundry Agent Service の
Function Tools** として登録し、エージェントがリアルタイムで検索・取得します。

| 従来（プレインデックス） | MCP サーバー | Function Tools（本ラボ） |
|--------------------------|-------------|--------------------------|
| 事前に全ファイルを取得・Embedding化 | 独立プロセスで MCP プロトコル提供 | Agent Service のツール定義として登録 |
| インデックス更新のラグがある | クライアント側で MCP 接続が必要 | クライアント側で直接 API 呼び出し |
| 大量のストレージ・コスト | 追加サーバー運用が必要 | サーバー不要、コードのみ |

## Step 1: Function Tools の構造を理解する

`src/tools/github_tools.py` が提供する3つのツール:

| ツール名 | 機能 | 使用シーン |
|---------|------|-----------|
| `list_repository_files` | ファイル一覧取得 | リポジトリ構造の把握 |
| `get_file_content` | ファイル内容取得 | 設計書やソースの詳細確認 |
| `search_code` | コード検索 | 関数名やクラス名での検索 |

### ツールスキーマの定義（Responses API 形式）

```python
GITHUB_FUNCTION_TOOLS = [
    {
        "type": "function",
        "name": "search_code",
        "description": "GitHub リポジトリ内でコードを検索する",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "検索キーワード"},
                "owner": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    # get_file_content, list_repository_files ...
]
```

### ディスパッチロジック

```python
def dispatch(function_name: str, arguments: dict) -> str:
    """Function Tool の呼び出しをルーティングする."""
    handlers = {
        "search_code": search_code,
        "get_file_content": get_file_content,
        "list_repository_files": list_repository_files,
    }
    handler = handlers.get(function_name)
    if handler is None:
        return json.dumps({"error": f"Unknown function: {function_name}"})
    return handler(**arguments)
```

## Step 2: GitHub API 関数の実装

### コード検索

```python
def search_code(query: str, owner: str = "", repo: str = "") -> str:
    """GitHub Code Search API でコードを検索する."""
    q = query
    _owner = owner or github_cfg.owner
    _repo = repo or github_cfg.repo
    if _owner and _repo:
        q += f" repo:{_owner}/{_repo}"

    data = _github_get("https://api.github.com/search/code", {"q": q, "per_page": 10})
    # 結果を整形して返す ...
```

### ファイル内容取得

```python
def get_file_content(path: str, owner: str = "", repo: str = "", ref: str = "main") -> str:
    """GitHub Contents API でファイル内容を取得する."""
    url = f"https://api.github.com/repos/{_owner}/{_repo}/contents/{path}"
    # Base64 デコードして返す ...
```

## Step 3: テスト

```python
from src.tools.github_tools import search_code, get_file_content, list_repository_files

# コード検索
print(search_code("authentication", owner="microsoft", repo="vscode"))

# ファイル内容取得
print(get_file_content("README.md", owner="microsoft", repo="vscode"))

# ファイル一覧
print(list_repository_files(owner="microsoft", repo="vscode", extensions=".md"))
```

## Step 4: Agent Service との統合

Function Tools はクライアント側（`agent_client.py`）で実行されます:

1. ユーザーの質問を Agent Service に送信
2. Agent が GitHub ツールの呼び出しを決定
3. レスポンスに `function_call` アイテムが含まれる
4. クライアントが `dispatch()` で実際の API 呼び出しを実行
5. 結果を `function_call_output` として Agent に返送
6. Agent が最終回答を生成

```
ユーザー → Agent Service → "search_code が必要"
                               ↓
Agent Client ← function_call(name="search_code", args={...})
    ↓
dispatch("search_code", args) → GitHub API → 結果
    ↓
Agent Client → function_call_output(result) → Agent Service
                               ↓
                         最終回答をユーザーに返す
```

## 💡 発展的なトピック

- **カスタムツールの追加**: `GITHUB_FUNCTION_TOOLS` にスキーマを追加し、`dispatch()` にハンドラを登録
- **他のデータソース**: Azure DevOps、Confluence、Jira なども同様に Function Tools 化可能
- **認証の強化**: OAuth App や GitHub App による安全なトークン管理

## ✅ チェックポイント

- [ ] `github_tools.py` の 3 つの関数が正常動作する
- [ ] `search_code` で対象リポジトリのコード検索結果が返る
- [ ] `get_file_content` でファイルの内容が表示される
- [ ] `list_repository_files` でファイル一覧が取得できる
- [ ] `GITHUB_FUNCTION_TOOLS` スキーマが Responses API 形式で定義されている

---

**次のステップ:** [Module 3: Foundry IQ ナレッジベース構築](module3-foundry-iq.md)
