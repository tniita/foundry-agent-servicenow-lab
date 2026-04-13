"""認証依存性 — JWT トークン検証とユーザー情報抽出."""

import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Bearer トークンからユーザー情報を抽出する.

    JWT を検証し、ペイロードを返す。
    無効なトークンまたは期限切れの場合は 401 エラーを返す。
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            issuer="https://bizportal-api.example.co.jp",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンが期限切れです。再ログインしてください。",
        )
    except jwt.InvalidTokenError as e:
        logger.warning("無効なトークン: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効な認証トークンです。",
        )


async def require_role(required_role: str):
    """特定ロールを要求するデコレータ生成関数.

    使用例:
        @router.post("/admin-only")
        async def admin_action(user=Depends(require_role("admin"))):
            ...
    """
    async def role_checker(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        user_role = current_user.get("role", "employee")
        role_hierarchy = {"admin": 3, "manager": 2, "employee": 1}
        if role_hierarchy.get(user_role, 0) < role_hierarchy.get(required_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"この操作には {required_role} 以上の権限が必要です。",
            )
        return current_user

    return role_checker
