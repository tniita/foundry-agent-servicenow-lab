"""データベース接続・セッション管理."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

# 非同期エンジン作成
# 接続プール設定は settings から取得 (DOC-DB-001 3.1 参照)
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,  # コネクション有効性チェック
    echo=settings.debug,
)

# セッションファクトリ
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 宣言的ベースクラス."""
    pass


async def get_db() -> AsyncSession:
    """リクエストごとの DB セッションを提供する依存性.

    FastAPI の Depends で注入し、リクエスト終了時に自動クローズする。
    接続プール使用率が80%を超えた場合は Azure Monitor でアラートが発報される。
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
