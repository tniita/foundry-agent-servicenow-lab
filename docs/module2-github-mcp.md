# Module 2: GitHub MCPTool (Remote MCP) 構築

## 学習目標

- Foundry Agent Service の MCPTool の仕組みを理解する
- GitHub リモート MCP サーバーを利用したコード・設計書検索を構築する
- プロジェクト接続 (RemoteTool) の作成方法を理解する

## 概要

GitHub が提供するリモート MCP サーバー (`https://api.githubcopilot.com/mcp`) を
**Foundry Agent Service の MCPTool** として登録し、エージェントがサーバーサイドで
リアルタイムにコード検索・ファイル取得を行います。

| 従来（プレインデックス） | Function Tools | MCPTool（本ラボ） |
|--------------------------|----------------|-------------------|
| 事前に全ファイルを取得・Embedding化 | クライアント側で API 呼び出し | サーバーサイドで自動実行 |
| インデックス更新のラグがある | dispatch ループが必要 | クライアント側の dispatch 不要 |
| 大量のストレージ・コスト | カスタムコードの保守が必要 | プロジェクト接続のみで動作 |

## Step 1: GitHub Remote MCP Server を理解する

GitHub が提供する MCP エンドポイント:
- **URL:** `https://api.githubcopilot.com/mcp`
- **認証:** GitHub Personal Access Token (Bearer)
- **提供ツール:** `search_code`, `get_file_contents`, `list_repository_files` 等

### Foundry Agent Service での MCPTool 構成

```python
from azure.ai.projects.models import MCPTool

# MCPTool: GitHub リモート MCP サーバー（カタログツール形式）
mcp_github_tool = MCPTool(
    server_label="GitHub",
    server_url="https://api.githubcopilot.com/mcp",
    require_approval="never",
    project_connection_id="GitHub",
)
```

## Step 2: プロジェクト接続の作成

GitHub MCP 接続は `CustomKeys` 認証タイプで作成します:

```python
# GitHub MCP 接続（CustomKeys 認証）
connection_body = {
    "name": "GitHub",
    "properties": {
        "authType": "CustomKeys",
        "category": "RemoteTool",
        "target": "https://api.githubcopilot.com/mcp",
        "isSharedToAll": True,
        "credentials": {
            "keys": {
                "Authorization": f"Bearer {github_token}",
            },
        },
        "metadata": {"ApiType": "GitHub"},
    },
}
```

セットアップスクリプトで自動作成:

```bash
python -m scripts.setup_agent
```

## Step 3: MCPTool と Function Tools の違い

```
【MCPTool（サーバーサイド実行）】
ユーザー → Agent Service → MCPTool 呼び出し → GitHub MCP Server
                               ↓ (サーバー内で自動実行)
                         最終回答をユーザーに返す

【旧 Function Tools（クライアント側実行）】
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

MCPTool ではクライアント側の dispatch ループが完全に不要になり、
コード量と遅延が大幅に削減されます。

## Step 4: テスト

```bash
# E2E テスト（GitHub MCP 経由でエージェントが回答できることを検証）
pytest tests/test_github_mcp.py -v
```

## 💡 発展的なトピック

- **カタログツール**: Foundry ポータルのカタログから GitHub を追加し、ポータル上でも利用可能
- **他の MCP サーバー**: Azure DevOps、Confluence なども同様に MCPTool として追加可能
- **認証の強化**: OAuth App や GitHub App によるトークン管理

## ✅ チェックポイント

- [ ] GitHub Personal Access Token が `.env` に設定されている
- [ ] プロジェクト接続 `GitHub` が作成されている
- [ ] `tests/test_github_mcp.py` が正常に通る
- [ ] エージェントが GitHub MCP 経由でコード検索結果を返す

---

**次のステップ:** [Module 3: Foundry IQ ナレッジベース構築](module3-foundry-iq.md)
