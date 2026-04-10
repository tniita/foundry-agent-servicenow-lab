# Module 1: モック CSV データ + Blob アップロード

## 学習目標

- ServiceNow のインシデントデータ構造を理解する
- モック CSV データを Azure Blob Storage にアップロードする
- Blob Knowledge Source がデータを自動処理する仕組みを学ぶ

## 概要

本ハンズオンでは ServiceNow の代わりにモック CSV ファイル (`data/mock_incidents.csv`) を使用します。
CSV を Blob Storage にアップロードすると、Blob Knowledge Source が自動的に:
- データソース、スキルセット、インデックス、インデクサーを生成
- テキスト抽出 → チャンキング → Embedding 生成 → インデックス化を実行

実運用では ServiceNow REST API からエクスポートした CSV に置き換え可能です。

## Step 1: モック CSV の確認

```bash
# 先頭3行を確認
python -c "
import csv
with open('data/mock_incidents.csv', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 3: break
        print(f\"{row['number']}: {row['short_description']}\")
        print(f\"  カテゴリ: {row['category']} / 優先度: {row['priority']} / 状態: {row['state']}\")
        print()
"
```

### CSV カラム構成

| カラム | 説明 | 例 |
|--------|------|-----|
| `sys_id` | ServiceNow 内部 ID | `a1b2c3d4e5f60001` |
| `number` | インシデント番号 | `INC0001001` |
| `short_description` | タイトル | `社内ポータルにログインできない` |
| `description` | 詳細説明 | 障害の詳細な状況 |
| `category` | カテゴリ | `ソフトウェア`, `ネットワーク`, `セキュリティ` |
| `priority` | 優先度 (1=最高, 4=低) | `1` |
| `state` | 状態 (1=新規, 2=進行中, 6=解決, 7=クローズ) | `7` |
| `resolution_notes` | 解決メモ | 原因と対処の詳細 |

## Step 2: Blob Storage へのアップロード

セットアップスクリプトで自動アップロードできます:

```bash
python -m scripts.setup_knowledge --skip-upload  # KB作成だけの場合
python -m scripts.setup_knowledge                 # アップロード + KB作成
```

### 手動アップロード（Azure CLI）

```bash
az storage blob upload \
  --account-name <storage-account-name> \
  --container-name incidents \
  --name mock_incidents.csv \
  --file data/mock_incidents.csv \
  --auth-mode key
```

### Python でのアップロード

```python
from azure.storage.blob import BlobServiceClient

blob_service = BlobServiceClient.from_connection_string("<connection-string>")
container = blob_service.get_container_client("incidents")

with open("data/mock_incidents.csv", "rb") as f:
    container.upload_blob("mock_incidents.csv", f, overwrite=True)
```

## Step 3: Blob → Knowledge Source の自動処理

Blob にアップロードされたデータは、Module 3 で作成する Blob Knowledge Source により自動的に処理されます:

```
Blob Storage (CSV)
    ↓ (自動) Blob Knowledge Source が生成:
    ├─ Data Source: incidents-blob-ks-datasource
    ├─ Skillset:    incidents-blob-ks-skillset
    │                 ├─ テキスト抽出
    │                 ├─ チャンキング
    │                 └─ text-embedding-3-large でベクトル化
    ├─ Index:       incidents-blob-ks-index
    └─ Indexer:     incidents-blob-ks-indexer (定期実行)
```

> **Note:** 従来の手動インデクサー (`csv_indexer.py`) は不要になりました。
> Blob Knowledge Source がインデックス管理を完全に自動化します。

## 💡 カスタマイズのヒント

- **実際の ServiceNow から CSV エクスポート**: ServiceNow の List View → Export → CSV
- **複数ファイル対応**: Blob コンテナに複数の CSV や PDF を配置可能
- **増分更新**: インデクサーが自動的に新規/変更ファイルを検出して更新

## ✅ チェックポイント

- [ ] `data/mock_incidents.csv` に 25 件のインシデントデータがある
- [ ] Blob Storage の `incidents` コンテナにファイルがアップロードされた
- [ ] Azure Portal → Storage Account → コンテナで CSV が確認できる

---

**次のステップ:** [Module 2: GitHub MCP サーバー構築](module2-github-mcp.md)
