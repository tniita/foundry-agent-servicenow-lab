# Module 4: Foundry Agent Service + Streamlit UI

## 学習目標

- Foundry Agent Service の Prompt Agent を作成する
- MCPTool (Foundry IQ KB) と Function Tools (GitHub) を統合したエージェントを構築する
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
  → Agent Service: search_code (Function Tool) の呼び出しを決定
  → クライアントが GitHub API を実行して結果を返送
  → 回答: "src/auth/authenticator.py に認証ロジックがあります..."
```

## Step 1: エージェントの作成

### セットアップスクリプトの実行

```bash
# RemoteTool 接続 + Prompt Agent を作成
python -m scripts.setup_agent

# オプション:
#   --skip-connection   接続作成をスキップ
#   --skip-agent        エージェント作成をスキップ
```

### Prompt Agent の構成

```python
from azure.ai.projects.models import MCPTool, PromptAgentDefinition

# MCPTool: Foundry IQ KB (サーバー側自動実行)
mcp_kb_tool = MCPTool(
    server_label="knowledge-base",
    server_url=mcp_endpoint,
    require_approval="never",
    allowed_tools=["knowledge_base_retrieve"],
    project_connection_id=connection_name,
)

agent = project_client.agents.create_version(
    agent_name="system-inquiry-agent",
    definition=PromptAgentDefinition(
        model="gpt-4o",
        instructions=AGENT_INSTRUCTIONS,
        tools=[mcp_kb_tool],  # MCPTool はエージェント定義に含める
    ),
)
```

## Step 2: Responses API によるエージェント呼び出し

### 基本フロー

```python
from azure.ai.projects import AIProjectClient
from src.tools.github_tools import GITHUB_FUNCTION_TOOLS, dispatch

project_client = AIProjectClient(endpoint=endpoint, credential=credential)
openai_client = project_client.get_openai_client()

# 会話を作成
conversation = openai_client.conversations.create()

# エージェントにリクエスト送信
response = openai_client.responses.create(
    input="VPN 障害のインシデントはある？",
    tools=GITHUB_FUNCTION_TOOLS,        # Function Tools はリクエスト時に渡す
    conversation=conversation.id,
    extra_body={
        "agent_reference": {
            "name": "system-inquiry-agent",
            "type": "agent_reference",
        }
    },
)
```

### Function Tool 実行ループ

Agent が GitHub ツールを呼び出した場合、クライアント側で実行して結果を返送します:

```python
for round in range(max_tool_rounds):
    # Function Call アイテムを抽出
    function_calls = [item for item in response.output if item.type == "function_call"]
    if not function_calls:
        break  # テキスト回答が得られた

    # 各 Function を実行
    tool_results = []
    for fc in function_calls:
        result = dispatch(fc.name, json.loads(fc.arguments))
        tool_results.append({
            "type": "function_call_output",
            "call_id": fc.call_id,
            "output": result,
        })

    # 結果を送り返す
    response = openai_client.responses.create(
        input=tool_results,
        tools=GITHUB_FUNCTION_TOOLS,
        conversation=conversation.id,
        extra_body={"agent_reference": {...}},
    )

# 最終回答を取得
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
| ツール呼び出し表示 | GitHub Function Tools の呼び出し履歴を展開表示 |
| パフォーマンス指標 | 応答時間の表示 |
| サイドバー | Agent Service 情報と会話クリアボタン |

### テスト用の質問例

```
# インシデント検索 (→ MCPTool → Foundry IQ KB)
「VPN 接続が不安定になる問題の解決方法を教えてください」
「過去にデータベースのバックアップが失敗したインシデントはありますか？」
「優先度1のインシデントの一覧を教えてください」

# コード検索 (→ Function Tools → GitHub API)
「認証モジュールのソースコードを見せてください」
「README.md の内容を教えてください」
「このリポジトリのディレクトリ構造を教えてください」

# 複合質問 (→ MCPTool + Function Tools)
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

### 新しい Function Tool の追加

1. `src/tools/github_tools.py` の `GITHUB_FUNCTION_TOOLS` にスキーマを追加
2. 関数を実装
3. `dispatch()` のハンドラマップに追加

## ✅ チェックポイント

- [ ] `python -m scripts.setup_agent` が正常完了する
- [ ] `streamlit run src/app.py` でチャット UI が起動する
- [ ] インシデントに関する質問で Foundry IQ KB の結果が返る
- [ ] コードに関する質問で GitHub API の結果が返る
- [ ] ツール呼び出し履歴が UI に表示される
- [ ] 会話の文脈が維持される（フォローアップ質問が機能する）

---

**次のステップ:** [Module 5: 統合テストと品質評価](module5-testing.md)
