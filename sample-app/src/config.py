"""アプリケーション設定 — 環境変数から各サービスの接続情報を読み込む."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """アプリケーション全体の設定."""

    # アプリケーション基本設定
    app_name: str = "BizPortal"
    debug: bool = False

    # Azure AD 認証設定
    azure_ad_tenant_id: str = os.getenv("AZURE_AD_TENANT_ID", "")
    azure_ad_client_id: str = os.getenv("AZURE_AD_CLIENT_ID", "")
    azure_ad_client_secret: str = os.getenv("AZURE_AD_CLIENT_SECRET", "")
    azure_ad_redirect_uri: str = os.getenv(
        "AZURE_AD_REDIRECT_URI", "https://bizportal.example.co.jp/callback"
    )

    # JWT 設定
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    jwt_algorithm: str = "RS256"
    jwt_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 7

    # PostgreSQL 設定
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://bizportal:password@localhost:5432/bizportal",
    )
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # Redis 設定
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_session_ttl: int = 3600  # セッションキャッシュ TTL（秒）

    # Azure Blob Storage 設定
    blob_connection_string: str = os.getenv("BLOB_CONNECTION_STRING", "")
    blob_receipts_container: str = "receipts"
    blob_max_file_size_mb: int = 10

    # Microsoft Graph API 設定 (メール送信用)
    graph_api_endpoint: str = "https://graph.microsoft.com/v1.0"
    graph_client_id: str = os.getenv("GRAPH_CLIENT_ID", "")
    graph_client_secret: str = os.getenv("GRAPH_CLIENT_SECRET", "")

    # CORS 設定
    cors_origins: list[str] = [
        "https://bizportal.example.co.jp",
        "https://bizportal-stg.example.co.jp",
    ]

    # SMTP 設定 (Exchange Online フォールバック用)
    smtp_timeout: int = 30  # タイムアウト秒 (INC0001002 対策)
    smtp_retry_count: int = 3
    smtp_retry_base_delay: int = 5  # 指数バックオフの初回待機秒

    # 通知レート制限
    notification_rate_limit: int = 50  # 件/分

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
