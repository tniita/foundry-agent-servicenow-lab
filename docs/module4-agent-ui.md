# Module 4: Foundry Agent Service + Streamlit UI

## 学習目標

- Foundry Agent Service の Prompt Agent を作成する
- MCPTool (Foundry IQ KB) と MCPTool (GitHub Remote MCP) を統合したエージェントを構築する
- Responses API でエージェントを呼び出すクライアントを実装する
- Streamlit でインタラクティブなチャット UI を構築する

## 概要

Foundry Agent Service は、ツール選択・実行のオーケストレーションをサーバー側で管理します。
従来の自前 Function Calling ループと比較して、以下の利点があります:

| 従来 (Function Calling) | Foundry Agent Service |
|-------------------------|----------------------|
| クライアントで全ツール管理 | MCPTool はサーバー側で自動実行 |
| 自前でループ・エラーハンドリング | Agent が判断・実行・リトライ |
| 会話管理は自前で実装 | Conversations API でサーバー側管理 |

```
ユーザー: "VPN 接続が切れる問題は過去にあった？"
  → Agent Service: knowledge_base_retrieve (MCPTool) を自動呼び出し
  → Foundry IQ KB からアジェンティック検索
  → 回答: "INC0001003 で同様の事例があります..."

ユーザー: "認証モジュールのソースコードを見せて"
  → Agent Service: search_code (GitHub MCPTool) をサーバーサイドで自動実行
  → GitHub リモート MCP サーバーからコード取得
  → 回答: "src/auth/authenticator.py に認証ロジックがあります..."
```

## Step 1: エージェントの作成

### セットアップスクリプトの実行

```bash
# RemoteTool 接続 (KB MCP + GitHub MCP) + Prompt Agent を作成
python -m scripts.setup_agent

# オプション:
#   --skip-connection   接続作成をスキップ
#   --skip-agent        エージェント作成をスキップ
```

### Prompt Agent の構成

```python
from azure.ai.projects.models import MCPTool, PromptAgentDefinition

# MCPTool 1: Foundry IQ KB (サーバー側自動実行)
mcp_kb_tool = MCPTool(
    server_label="knowledge-base",
    server_url=mcp_endpoint,
    require_approval="never",
    allowed_tools=["knowledge_base_retrieve"],
    project_connection_id=connection_name,
)

# MCPTool 2: GitHub Remote MCP (サーバー側自動実行)
mcp_github_tool = MCPTool(
    server_label="GitHub",
    server_url="https://api.githubcopilot.com/mcp",
    require_approval="never",
    project_connection_id="GitHub",
)

agent = project_client.agents.create_version(
    agent_name="system-inquiry-agent",
    definition=PromptAgentDefinition(
        model="gpt-4o",
        instructions=AGENT_INSTRUCTIONS,
        tools=[mcp_kb_tool, mcp_github_tool],  # 両ツールともサーバー側で自動実行
    ),
)
```

## Step 2: Responses API によるエージェント呼び出し

### 基本フロー

```python
from azure.ai.projects import AIProjectClient

project_client = AIProjectClient(endpoint=endpoint, credential=credential)
openai_client = project_client.get_openai_client()

# 会話を作成
conversation = openai_client.conversations.create()

# エージェントにリクエスト送信
# 両 MCPTool はサーバーサイドで自動実行されるため、
# クライアント側の dispatch ループは不要
response = openai_client.responses.create(
    input="VPN 障害のインシデントはある？",
    conversation=conversation.id,
    extra_body={
        "agent_reference": {
            "name": "system-inquiry-agent",
            "type": "agent_reference",
        }
    },
)

# 最終回答を取得（dispatch ループ不要）
print(response.output_text)
```

## Step 3: Streamlit UI

```bash
streamlit run src/app.py
```

### UI の機能

| 機能 | 説明 |
|------|------|
| チャット入力 | 自然言語でシステムについて質問 |
| 会話履歴 | Conversations API によるマルチターン管理 |
| ツール呼び出し表示 | MCPTool の呼び出し履歴を展開表示 |
| パフォーマンス指標 | 応答時間の表示 |
| サイドバー | Agent Service 情報と会話クリアボタン |

### テスト用の質問例

```
# インシデント検索 (→ MCPTool → Foundry IQ KB)
「VPN 接続が不安定になる問題の解決方法を教えてください」
「過去にデータベースのバックアップが失敗したインシデントはありますか？」
「優先度1のインシデントの一覧を教えてください」

# コード検索 (→ GitHub MCPTool → GitHub Remote MCP Server)
「認証モジュールのソースコードを見せてください」
「README.md の内容を教えてください」
「このリポジトリのディレクトリ構造を教えてください」

# 複合質問 (→ KB MCPTool + GitHub MCPTool)
「ログインエラーが発生しています。過去の同様のインシデントと、関連するソースコードを確認してください」
```

## Step 4: カスタマイズ

### エージェント指示の変更

`scripts/setup_agent.py` の `instructions` 変数を編集して再実行:

```python
instructions = """
あなたは社内 IT システムの問い合わせ対応エージェントです。
# ここにドメイン固有のルールを追加
- 社外秘情報は回答に含めないこと
- セキュリティインシデントは必ずエスカレーションを推奨すること
"""
```

```bash
python -m scripts.setup_agent --skip-connection
```

### 新しい MCPTool の追加

1. プロジェクト接続（RemoteTool カテゴリ）を作成
2. `setup_agent.py` に MCPTool 定義を追加
3. エージェントの instructions に新ツールの説明を追加

## ✅ チェックポイント

- [ ] `python -m scripts.setup_agent` が正常完了する
- [ ] `streamlit run src/app.py` でチャット UI が起動する
- [ ] インシデントに関する質問で Foundry IQ KB の結果が返る
- [ ] コードに関する質問で GitHub MCPTool の結果が返る
- [ ] 会話の文脈が維持される（フォローアップ質問が機能する）

---

**次のステップ:** [Module 5: 統合テストと品質評価](module5-testing.md)
