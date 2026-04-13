# インフラ構成設計書 — 社内業務ポータル (BizPortal)

| 項目 | 内容 |
|------|------|
| ドキュメント ID | DOC-INFRA-001 |
| バージョン | 1.3 |
| クラウド | Microsoft Azure (Japan East) |
| 最終更新日 | 2025-03-20 |

---

## 1. Azure リソース構成

### 1.1 リソースグループ

| リソースグループ | 用途 |
|----------------|------|
| rg-bizportal-prod | 本番環境 |
| rg-bizportal-stg | ステージング環境 |
| rg-bizportal-dev | 開発環境 |

### 1.2 リソース一覧（本番環境）

| リソース | SKU | 構成 |
|---------|-----|------|
| Azure App Service | P1v3 (2vCPU, 8GB) | 最小 2 インスタンス、最大 5 |
| Azure API Management | Standard | レート制限: 100 req/min/key |
| Azure Database for PostgreSQL | GP_Standard_D2ds_v4 | HA 有効、35 日バックアップ |
| Azure Cache for Redis | C1 Standard (1GB) | セッションキャッシュ |
| Azure Blob Storage | Standard_GRS | 領収書・添付ファイル保存 |
| Azure Key Vault | Standard | シークレット・証明書管理 |
| Application Insights | — | APM・ログ収集 |
| Azure Monitor | — | アラート・ダッシュボード |

### 1.3 ネットワーク構成

```
┌─────────────────────────────────────────────────┐
│              Azure Virtual Network               │
│              10.0.0.0/16                         │
│                                                  │
│  ┌─────────────────┐  ┌──────────────────────┐  │
│  │ App Subnet       │  │ DB Subnet            │  │
│  │ 10.0.1.0/24      │  │ 10.0.2.0/24          │  │
│  │                  │  │                      │  │
│  │ App Service      │  │ PostgreSQL           │  │
│  │ (VNet 統合)      │──│ (Private Endpoint)   │  │
│  │                  │  │                      │  │
│  └─────────────────┘  └──────────────────────┘  │
│                                                  │
│  ┌─────────────────┐  ┌──────────────────────┐  │
│  │ Cache Subnet     │  │ PE Subnet            │  │
│  │ 10.0.3.0/24      │  │ 10.0.4.0/24          │  │
│  │                  │  │                      │  │
│  │ Redis Cache      │  │ Key Vault PE         │  │
│  │ (Private EP)     │  │ Blob Storage PE      │  │
│  └─────────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## 2. App Service 設定

### 2.1 アプリケーション設定

| 設定名 | 値 | 説明 |
|--------|-----|------|
| SCM_DO_BUILD_DURING_DEPLOYMENT | true | デプロイ時にビルド実行 |
| WEBSITES_ENABLE_APP_SERVICE_STORAGE | true | 永続ストレージ有効化 |
| WEBSITE_HEALTHCHECK_MAXPINGFAILURES | 5 | ヘルスチェック失敗上限 |

### 2.2 スケーリング設定

```
自動スケール規則:
  スケールアウト: CPU > 70% (5分平均) → +1 インスタンス (最大5)
  スケールイン:  CPU < 30% (10分平均) → -1 インスタンス (最小2)
```

**重要:** 最小インスタンス数は必ず 1 以上を設定すること。
0 に設定するとスケールイン後にアプリが応答不能になる。
（参考: INC0001018 — Azure Bot Service で最小インスタンス0によりサービス停止が発生）

### 2.3 デプロイスロット

| スロット | 用途 |
|---------|------|
| production | 本番トラフィック処理 |
| staging | デプロイ前の最終確認 |

デプロイフロー: `staging` にデプロイ → 動作確認 → スロットスワップで `production` に昇格

---

## 3. Azure API Management

### 3.1 レート制限ポリシー

```xml
<rate-limit calls="100" renewal-period="60" />
<quota calls="10000" renewal-period="86400" />
```

### 3.2 CORS ポリシー

```xml
<cors allow-credentials="true">
  <allowed-origins>
    <origin>https://bizportal.example.co.jp</origin>
    <origin>https://bizportal-stg.example.co.jp</origin>
  </allowed-origins>
  <allowed-methods>
    <method>GET</method>
    <method>POST</method>
    <method>PUT</method>
    <method>DELETE</method>
  </allowed-methods>
  <allowed-headers>
    <header>Authorization</header>
    <header>Content-Type</header>
  </allowed-headers>
</cors>
```

**注意:** CORS 設定はデプロイのたびに確認すること。CDN/APIM の設定が欠落するとファイルアップロードが失敗する（INC0001006 参考）。

### 3.3 IP ブロックリスト

Bot 攻撃対策として、WAF ルールで自動ブロックを実装。
- 5 分間で 500 リクエスト超過 → 自動ブロック（1 時間）
- 正規クライアントは専用サブスクリプションキーで優先枠を確保
- 参考: INC0001013 で Bot 攻撃によりレート制限枠が消費された事例あり

---

## 4. CI/CD パイプライン

### 4.1 Azure DevOps Pipeline

```yaml
trigger:
  branches:
    include:
      - main
      - release/*

stages:
  - stage: Build
    jobs:
      - job: BuildAndTest
        pool:
          name: 'Self-Hosted-Linux'
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.11'
          - script: |
              pip install -r requirements.txt
              pytest tests/ --cov=src --cov-report=xml
          - task: PublishCodeCoverageResults@2

  - stage: DeployStaging
    dependsOn: Build
    jobs:
      - deployment: DeployToStaging
        environment: 'bizportal-staging'
        strategy:
          runOnce:
            deploy:
              steps:
                - task: AzureWebApp@1
                  inputs:
                    azureSubscription: 'Azure-Production'
                    appName: 'bizportal-api'
                    deployToSlotOrASE: true
                    slotName: 'staging'

  - stage: DeployProduction
    dependsOn: DeployStaging
    jobs:
      - deployment: SwapSlots
        environment: 'bizportal-production'
        strategy:
          runOnce:
            deploy:
              steps:
                - task: AzureAppServiceManage@0
                  inputs:
                    Action: 'Swap Slots'
                    SourceSlot: 'staging'
```

### 4.2 ビルドエージェント管理

- Self-hosted エージェントは Docker ベース
- Docker イメージキャッシュの肥大化によりディスク不足が発生する可能性あり
- 日次で `docker system prune` を実行するクリーンアップジョブを設定すること
- 参考: INC0001015 でエージェントプール全停止が発生

---

## 5. SSL/TLS 証明書

| ドメイン | 発行元 | 有効期限 | 自動更新 |
|---------|--------|---------|---------|
| bizportal.example.co.jp | DigiCert | 2026-01-15 | Yes (Key Vault) |
| bizportal-api.example.co.jp | DigiCert | 2026-01-15 | Yes (Key Vault) |
| *.example.co.jp (ワイルドカード) | DigiCert | 2026-03-01 | Yes (Key Vault) |

---

## 6. DNS 構成

| レコード | 種別 | 値 |
|---------|------|-----|
| bizportal.example.co.jp | CNAME | bizportal.azurewebsites.net |
| bizportal-api.example.co.jp | CNAME | bizportal-apim.azure-api.net |

**DNS 解決の注意:**
- 内部 DNS サーバー経由の場合、フォワーダーの遅延が原因で名前解決が遅くなる場合がある
- nslookup で応答時間が 1 秒を超える場合は DNS フォワーダー設定を確認すること
- 参考: INC0001023 で DNS 解決遅延の調査中

---

## 7. 仮想マシン管理（バッチサーバー）

月次バッチ処理用の VM:

| 項目 | 設定 |
|------|------|
| VM サイズ | Standard_D4s_v3 |
| OS | Ubuntu 22.04 LTS |
| 可用性 | 可用性ゾーン 1 |
| 自動起動 | Azure Automation Runbook |

**重要:** Azure のホストメンテナンスで VM が予告なく停止する場合がある。
可用性ゾーンへの配置と自動起動スクリプトの設定を必ず行うこと（INC0001021 の教訓）。
