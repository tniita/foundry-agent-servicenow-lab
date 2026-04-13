"""認証 API エンドポイント — Azure AD 連携 SSO."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.auth.service import AuthService
from src.auth.dependencies import get_current_user

router = APIRouter()


class LoginRequest(BaseModel):
    """Azure AD 認可コードによるログインリクエスト."""
    authorization_code: str
    redirect_uri: str


class RefreshRequest(BaseModel):
    """トークンリフレッシュリクエスト."""
    refresh_token: str


@router.post("/login")
async def login(request: LoginRequest):
    """Azure AD ログイン.

    Azure AD から取得した認可コードを使ってシステム内 JWT を発行する。
    認証エラーの場合は 401 を返す。

    AD サーバーの過負荷時に認証エラーが発生する場合がある (INC0001001 参考)。
    """
    auth_service = AuthService()
    try:
        result = await auth_service.authenticate_with_azure_ad(
            authorization_code=request.authorization_code,
            redirect_uri=request.redirect_uri,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"認証に失敗しました: {str(e)}",
        )


@router.post("/refresh")
async def refresh_token(request: RefreshRequest):
    """アクセストークンをリフレッシュする.

    リフレッシュトークンが無効または期限切れの場合は 401 を返す。
    """
    auth_service = AuthService()
    try:
        result = await auth_service.refresh_access_token(request.refresh_token)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンのリフレッシュに失敗しました",
        )


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """ログアウト — セッション無効化とリフレッシュトークンのリボーク."""
    auth_service = AuthService()
    await auth_service.revoke_session(current_user["sub"])
    return {"message": "ログアウトしました"}
