# 社内業務ポータルシステム (BizPortal)

## 概要

社内の勤怠管理・経費精算・通知配信を統合した業務ポータルシステムです。
Azure AD 連携による SSO 認証、REST API によるフロントエンド・モバイル対応を実現しています。

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| バックエンド | Python 3.11 / FastAPI |
| データベース | PostgreSQL 15 (Azure Database for PostgreSQL) |
| キャッシュ | Redis 7 (Azure Cache for Redis) |
| 認証 | Azure AD (MSAL) + JWT |
| ファイルストレージ | Azure Blob Storage |
| メール送信 | Exchange Online (Microsoft Graph API) |
| インフラ | Azure App Service / Azure Container Apps |
| CI/CD | Azure DevOps Pipelines |
| 監視 | Azure Monitor + Application Insights |

## モジュール構成

```
sample-app/
├── docs/                          # 設計書
│   ├── system-overview.md         # システム概要設計書
│   ├── api-specification.md       # API 仕様書
│   ├── database-design.md         # データベース設計書
│   ├── infrastructure.md          # インフラ構成設計書
│   └── security-design.md         # セキュリティ設計書
├── src/
│   ├── main.py                    # FastAPI エントリポイント
│   ├── config.py                  # アプリケーション設定
│   ├── auth/                      # 認証モジュール
│   │   ├── __init__.py
│   │   ├── router.py              # 認証 API エンドポイント
│   │   ├── service.py             # 認証ビジネスロジック
│   │   └── dependencies.py        # 認証依存性（JWT 検証）
│   ├── attendance/                # 勤怠管理モジュール
│   │   ├── __init__.py
│   │   ├── router.py              # 勤怠 API エンドポイント
│   │   └── service.py             # 勤怠ビジネスロジック
│   ├── expense/                   # 経費精算モジュール
│   │   ├── __init__.py
│   │   ├── router.py              # 経費 API エンドポイント
│   │   └── service.py             # 経費ビジネスロジック
│   ├── notification/              # 通知モジュール
│   │   ├── __init__.py
│   │   ├── router.py              # 通知 API エンドポイント
│   │   └── service.py             # 通知ビジネスロジック
│   └── models/                    # 共通データモデル
│       ├── __init__.py
│       ├── database.py            # DB 接続・セッション管理
│       └── schemas.py             # SQLAlchemy / Pydantic モデル
├── tests/
│   └── test_attendance.py         # 勤怠モジュールのユニットテスト
└── requirements.txt
```

## 起動方法

```bash
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## API ドキュメント

起動後に以下で確認:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
