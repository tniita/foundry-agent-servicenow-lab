# Module 0: 環境セットアップ + Azure リソースデプロイ

## 学習目標

- Azure リソースを Bicep テンプレートで一括プロビジョニングする
- Python 仮想環境と依存パッケージをセットアップする
- 環境変数を構成する

## Step 1: Azure リソースのデプロイ

### 1.1 Azure CLI にログイン

```bash
az login
az account set --subscription <your-subscription-id>
```

### 1.2 リソースグループ作成

```bash
az group create --name rg-fiqlab --location japaneast
```

### 1.3 Bicep テンプレートでデプロイ

```bash
az deployment group create \
  --resource-group rg-fiqlab \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

### デプロイされるリソース

| リソース | 用途 |
|---------|------|
| Azure AI Services (kind: AIServices) | Foundry リソース。gpt-4o / text-embedding-3-large モデルを含む |
| Foundry Project (accounts/projects) | AI Services 直下のプロジェクト。Agent Service のホスト |
| Azure AI Search (Basic) | Blob Knowledge Source + Foundry IQ KB のバックエンド |
| Storage Account + Blob コンテナ | インシデントデータ格納 (`incidents`) |
| ロール割り当て | AI Search ↔ Storage, AI Search ↔ AI Services, Project ↔ AI Search |

> **Note:** Hub レス構成を採用しているため、AI Hub や Key Vault は不要です。
> Project は `Microsoft.CognitiveServices/accounts/projects` リソースとして
> AI Services の直下に作成されます。

### 1.4 デプロイ出力を確認

```bash
az deployment group show \
  --resource-group rg-fiqlab \
  --name main \
  --query properties.outputs -o json
```

出力される値:
- `searchEndpoint` — AI Search エンドポイント
- `aiServicesEndpoint` — AI Services エンドポイント
- `storageAccountName` — Storage Account 名
- `projectName` — Foundry Project 名

## Step 2: Python 環境セットアップ

```bash
cd handson-lab
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## Step 3: 環境変数の設定

```bash
cp .env.example .env
```

`.env` ファイルを編集し、Bicep デプロイで作成されたリソースの接続情報を設定:

```ini
# Bicep 出力から取得
AZURE_SEARCH_ENDPOINT=https://<search-name>.search.windows.net
AZURE_OPENAI_ENDPOINT=https://<ais-name>.cognitiveservices.azure.com/
BLOB_CONNECTION_STRING=<Blob 接続文字列>
BLOB_CONTAINER_NAME=incidents
BLOB_STORAGE_ACCOUNT_NAME=<storage-account-name>

# Azure Portal → AI Search → キー から取得
AZURE_SEARCH_API_KEY=<admin-key>

# Azure Portal → AI Services → キーとエンドポイント から取得
AZURE_OPENAI_API_KEY=<api-key>

# Foundry Agent Service
PROJECT_ENDPOINT=https://<ais-name>.services.ai.azure.com/api/projects/<project-name>
PROJECT_RESOURCE_ID=/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<ais-name>/projects/<project-name>
PROJECT_CONNECTION_NAME=kb-mcp-connection
AGENT_NAME=system-inquiry-agent

# GitHub
GITHUB_TOKEN=<GitHub PAT>
GITHUB_OWNER=<org-or-user>
GITHUB_REPO=<repo-name>
```

> **Note:** `PROJECT_RESOURCE_ID` は Agent セットアップ時に必要です。
> Azure Portal → AI Project → プロパティ から ARM リソース ID を確認してください。
> Hub レス構成では `Microsoft.CognitiveServices/accounts/<ais>/projects/<project>` の形式です。

## 確認ポイント

- [ ] `az deployment group show` でリソースのエンドポイントが表示される
- [ ] `pip list` で `azure-ai-projects`, `azure-search-documents`, `openai`, `streamlit` が確認できる
- [ ] `.env` ファイルの全項目が設定済み

---

**次のステップ:** [Module 1: モック CSV データ + Blob アップロード](module1-mock-data.md)
