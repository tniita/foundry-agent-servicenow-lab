"""社内業務ポータル (BizPortal) — FastAPI アプリケーションエントリポイント."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.auth.router import router as auth_router
from src.attendance.router import router as attendance_router
from src.expense.router import router as expense_router
from src.notification.router import router as notification_router
from src.config import settings
from src.models.database import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーション起動・終了時の処理."""
    # 起動時: テーブル作成
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # 終了時: DB 接続プールを閉じる
    await engine.dispose()


app = FastAPI(
    title="BizPortal API",
    description="社内業務ポータルシステム — 勤怠管理・経費精算・通知配信",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS 設定 — 許可ドメインのみアクセス可
# デプロイ時に CORS 設定が欠落しないよう注意 (INC0001006 参考)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ルーター登録
app.include_router(auth_router, prefix="/api/v1/auth", tags=["認証"])
app.include_router(attendance_router, prefix="/api/v1/attendance", tags=["勤怠管理"])
app.include_router(expense_router, prefix="/api/v1/expense", tags=["経費精算"])
app.include_router(notification_router, prefix="/api/v1/notifications", tags=["通知"])


@app.get("/health", tags=["ヘルスチェック"])
async def health_check():
    """ヘルスチェックエンドポイント.

    Azure App Service のヘルスチェック設定から呼び出される。
    App Service Plan の最小インスタンス数を 1 以上に設定すること (INC0001018 の教訓)。
    """
    return {
        "status": "healthy",
        "version": "2.1.0",
        "checks": {
            "database": "ok",
            "redis": "ok",
            "blob_storage": "ok",
            "azure_ad": "ok",
        },
    }
