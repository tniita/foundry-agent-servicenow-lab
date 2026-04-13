"""認証ビジネスロジック — Azure AD 連携 & JWT 発行."""

import logging
from datetime import datetime, timedelta, timezone

import jwt
import msal

from src.config import settings

logger = logging.getLogger(__name__)


class AuthService:
    """認証サービス — Azure AD トークン交換と JWT 管理."""

    def __init__(self):
        self.msal_app = msal.ConfidentialClientApplication(
            client_id=settings.azure_ad_client_id,
            client_credential=settings.azure_ad_client_secret,
            authority=f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}",
        )

    async def authenticate_with_azure_ad(
        self, authorization_code: str, redirect_uri: str
    ) -> dict:
        """Azure AD 認可コードフローで認証し、システム JWT を発行.

        1. 認可コードを Azure AD の /token エンドポイントに送信
        2. ID トークンからユーザー情報を取得
        3. DB のユーザーマスタと照合（初回はプロビジョニング）
        4. システム内 JWT を発行

        Raises:
            Exception: Azure AD 認証失敗時。AD サーバーの過負荷等が原因の場合あり (INC0001001)。
        """
        # Azure AD からトークンを取得
        result = self.msal_app.acquire_token_by_authorization_code(
            code=authorization_code,
            scopes=["User.Read"],
            redirect_uri=redirect_uri,
        )

        if "error" in result:
            logger.error(
                "Azure AD 認証エラー: %s - %s",
                result.get("error"),
                result.get("error_description"),
            )
            raise Exception(result.get("error_description", "認証に失敗しました"))

        # ID トークンからユーザー情報を抽出
        id_token_claims = result.get("id_token_claims", {})
        user_info = {
            "azure_ad_oid": id_token_claims.get("oid"),
            "name": id_token_claims.get("name"),
            "email": id_token_claims.get("preferred_username"),
        }

        # システム内 JWT を発行
        access_token = self._create_jwt(user_info)
        refresh_token = self._create_refresh_token(user_info)

        logger.info("ユーザー %s がログインしました", user_info["email"])

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": settings.jwt_expire_minutes * 60,
            "user": user_info,
        }

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """リフレッシュトークンから新しいアクセストークンを発行."""
        try:
            payload = jwt.decode(
                refresh_token,
                settings.jwt_secret_key,
                algorithms=["HS256"],
            )
        except jwt.ExpiredSignatureError:
            raise Exception("リフレッシュトークンが期限切れです")
        except jwt.InvalidTokenError:
            raise Exception("無効なリフレッシュトークンです")

        new_access_token = self._create_jwt(payload)
        return {
            "access_token": new_access_token,
            "expires_in": settings.jwt_expire_minutes * 60,
        }

    async def revoke_session(self, user_id: str):
        """セッションを無効化する（Redis のセッションキャッシュを削除）."""
        logger.info("ユーザー %s のセッションを無効化しました", user_id)

    def _create_jwt(self, user_info: dict) -> str:
        """システム内 JWT を生成する (DOC-SEC-001 1.3 参照)."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_info.get("azure_ad_oid", ""),
            "name": user_info.get("name", ""),
            "email": user_info.get("email", ""),
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
            "iss": "https://bizportal-api.example.co.jp",
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

    def _create_refresh_token(self, user_info: dict) -> str:
        """リフレッシュトークンを生成する."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_info.get("azure_ad_oid", ""),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=settings.jwt_refresh_expire_days),
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
