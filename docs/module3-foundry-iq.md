# Module 3: Foundry IQ ナレッジベース構築 (IaC)

## 学習目標

- Foundry IQ のアーキテクチャとアジェンティック検索の仕組みを理解する
- Python SDK で Blob Knowledge Source と Knowledge Base をプログラム的に作成する
- `KnowledgeBaseRetrievalClient` でアジェンティック検索を実行する

## Foundry IQ とは？

Foundry IQ は Azure AI Search 上に構築された**エンタープライズ知識レイヤー**です。

### 従来の RAG との違い

```
従来の RAG:
  ユーザー質問 → Embedding → ベクトル検索 → Top-K 取得 → LLM に渡す → 回答
  (全てを自前で実装する必要がある)

Foundry IQ アジェンティック検索:
  ユーザー質問 → Foundry IQ が自動で:
    1. 質問を分解（サブクエリ生成）
    2. 最適なナレッジソースを選択
    3. ハイブリッド検索（ベクトル + キーワード）を並列実行
    4. 結果を評価・不足があれば再検索
    5. 回答を合成し、引用を付与
```

### Blob Knowledge Source の自動化

Blob Knowledge Source を使うと、手動でのインデックス構築が不要になります:

```
従来（手動）:
  CSV → csv_indexer.py → Embedding 生成 → AI Search Index 作成 → ドキュメントアップロード

Blob Knowledge Source（自動）:
  CSV → Blob Storage → Knowledge Source API → 自動で以下を生成:
    ├─ Data Source (Blob 接続)
    ├─ Skillset (チャンキング + Embedding)
    ├─ Index (ベクトル + テキスト)
    └─ Indexer (自動取り込み + 増分更新)
```

## Step 1: セットアップスクリプトで一括作成

```bash
# Blob アップロード + Knowledge Source + Knowledge Base を一括作成
python -m scripts.setup_knowledge --wait

# オプション:
#   --wait          インジェスト完了まで待機
#   --timeout 600   待機タイムアウト (秒)
#   --skip-upload   Blob アップロードをスキップ
#   --csv <path>    カスタム CSV ファイルを指定
```

### スクリプトの処理フロー

```
1. 📤 CSV → Blob Storage にアップロード
2. 🔧 Blob Knowledge Source を作成
     → AI Search が自動で data source / skillset / index / indexer を生成
3. 🔧 Knowledge Base を作成
     → Knowledge Source を紐付け、LLM 接続を設定
4. ⏳ インジェスト完了を待機（--wait 指定時）
```

## Step 2: Knowledge Source の仕組み

### Python SDK でのプログラム的作成

```python
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureBlobKnowledgeSource,
    AzureBlobKnowledgeSourceParameters,
    AzureOpenAIVectorizerParameters,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeSourceAzureOpenAIVectorizer,
    KnowledgeSourceIngestionParameters,
)

index_client = SearchIndexClient(
    endpoint="https://your-search.search.windows.net",
    credential=AzureKeyCredential("your-api-key"),
)

knowledge_source = AzureBlobKnowledgeSource(
    name="incidents-blob-ks",
    description="ServiceNow インシデントデータ",
    azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
        connection_string="<blob-connection-string>",
        container_name="incidents",
        ingestion_parameters=KnowledgeSourceIngestionParameters(
            embedding_model=KnowledgeSourceAzureOpenAIVectorizer(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url="https://your-openai.openai.azure.com/",
                    deployment_name="text-embedding-3-large",
                    model_name="text-embedding-3-large",
                )
            ),
        ),
    ),
)

index_client.create_or_update_knowledge_source(knowledge_source)
```

### Knowledge Base の作成

```python
from azure.search.documents.indexes.models import (
    KnowledgeBase,
    KnowledgeSourceReference,
    KnowledgeRetrievalLowReasoningEffort,
    KnowledgeRetrievalOutputMode,
)

knowledge_base = KnowledgeBase(
    name="system-inquiry-kb",
    knowledge_sources=[
        KnowledgeSourceReference(name="incidents-blob-ks"),
    ],
    models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=llm_params)],
    retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
    output_mode=KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS,
)

index_client.create_or_update_knowledge_base(knowledge_base)
```

## Step 3: Python SDK でのアジェンティック検索

```python
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalMediumReasoningEffort,
)

# クライアント初期化
client = KnowledgeBaseRetrievalClient(
    endpoint="https://your-search.search.windows.net",
    knowledge_base_name="system-inquiry-kb",
    credential=AzureKeyCredential("your-api-key"),
)

# リクエスト構築（source_params 不要 — KB が自動でソースを選択）
request = KnowledgeBaseRetrievalRequest(
    messages=[
        KnowledgeBaseMessage(
            role="user",
            content=[KnowledgeBaseMessageTextContent(
                text="ログインできないというインシデントの対処法は？"
            )],
        )
    ],
    retrieval_reasoning_effort=KnowledgeRetrievalMediumReasoningEffort(),
    include_activity=True,
)

# 検索実行
result = client.retrieve(request)

# 回答の取得
for resp in result.response:
    for content in resp.content:
        print(content.text)

# 引用の取得
for ref in result.references:
    print(f"[{ref.type}] Score: {ref.reranker_score}")
```

### 推論努力レベル

| レベル | 説明 | ユースケース |
|--------|------|------------|
| `minimal` | 単純なキーワードベース | 高速応答が必要な場合 |
| `low` | 軽い質問分解 | 標準的な問い合わせ |
| `medium` | 完全な質問分解 + 複数ソース統合 | 複雑な問い合わせ |

## Step 4: Agent Service との MCPTool 接続

Foundry IQ KB はエージェントから **MCPTool** 経由で利用されます。

### MCP エンドポイント

```
{search_endpoint}/knowledgebases/{kb_name}/mcp?api-version=2025-11-01-preview
```

### RemoteTool プロジェクト接続

Agent Service から KB に接続するには、プロジェクトに **RemoteTool 接続** を作成します:

```python
# setup_agent.py が自動で作成
# Hub レス構成では CognitiveServices/accounts/projects/connections を使用
response = requests.put(
    f"https://management.azure.com{project_resource_id}"
    f"/connections/{connection_name}?api-version=2025-12-01",
    json={
        "type": "Microsoft.CognitiveServices/accounts/projects/connections",
        "properties": {
            "authType": "ProjectManagedIdentity",
            "category": "RemoteTool",
            "target": mcp_endpoint,
            "audience": "https://search.azure.com/",
        },
    },
)
```

### Prompt Agent での MCPTool 定義

```python
from azure.ai.projects.models import MCPTool

mcp_kb_tool = MCPTool(
    server_label="knowledge-base",
    server_url=mcp_endpoint,
    require_approval="never",
    allowed_tools=["knowledge_base_retrieve"],
    project_connection_id=connection_name,
)
```

> **ポイント:** MCPTool は Agent Service 側で自動実行されるため、クライアント側での処理は不要です。エージェントが質問を分析し、KB への検索が必要と判断した場合に自動で `knowledge_base_retrieve` を呼び出します。

## Step 5: ラボコードでの確認（直接利用）

KB を Agent Service 経由ではなく、直接呼び出してテストすることもできます:

```python
from src.foundry_iq.kb_query_service import query_knowledge_base

result = query_knowledge_base(
    question="過去にネットワーク障害で発生したインシデントとその解決策を教えてください",
    reasoning_effort="medium",
)

print(f"回答: {result['answer']}")
print(f"引用数: {len(result['citations'])}")
print(f"検索時間: {result['timing']['kb_retrieval']:.2f}s")
```

## 💡 ポイント

- **Blob Knowledge Source の利点:** インデックス作成、スキルセット、Embedding 生成がすべて自動化される
- **`include_activity=True`** を設定すると、Foundry IQ がどのような検索プランを立てたかを確認できる（デバッグに有用）
- **会話コンテキスト:** `messages` に過去の会話履歴を含めると、文脈を考慮した検索が行われる
- **増分更新:** Blob に新しいファイルを追加すると、インデクサーが自動的に検出して更新

## ✅ チェックポイント

- [ ] `python -m scripts.setup_knowledge --wait` が正常完了する
- [ ] Azure Portal → AI Search → Knowledge Sources に `incidents-blob-ks` が表示される
- [ ] Azure Portal → AI Search → Knowledge Bases に `system-inquiry-kb` が表示される
- [ ] AI Search のインデクサーが正常にドキュメントを処理している
- [ ] Python SDK でアジェンティック検索が成功し、回答が返る

---

**次のステップ:** [Module 4: チャットエージェント + UI](module4-agent-ui.md)
