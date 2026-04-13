"""通知 API エンドポイント."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.models.database import get_db
from src.models.schemas import NotificationCreate
from src.notification.service import NotificationService

router = APIRouter()


@router.get("")
async def get_notifications(
    unread_only: bool = Query(False, description="未読のみ取得"),
    limit: int = Query(20, ge=1, le=100, description="取得件数"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """通知一覧取得.

    ユーザー向けの通知を新しい順に取得する。
    """
    service = NotificationService(db)
    return await service.get_notifications(
        user_id=current_user.get("sub", ""),
        unread_only=unread_only,
        limit=limit,
    )


@router.post("", status_code=201)
async def create_notification(
    request: NotificationCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """通知作成（管理者向け）.

    manager 以上の権限が必要。
    配信チャネル: in_app（アプリ内）、email（メール）、teams（Teams チャネル投稿）。

    メール送信時の注意:
    - SMTP タイムアウトは 30 秒に設定 (INC0001002 対策)
    - 送信失敗時は 3 回リトライ（指数バックオフ、初回 5 秒）
    - 大量配信は 50 件/分にレート制限
    """
    user_role = current_user.get("role", "employee")
    if user_role == "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="通知の作成には manager 以上の権限が必要です。",
        )

    service = NotificationService(db)
    return await service.create_notification(
        created_by=current_user.get("sub", ""),
        title=request.title,
        body=request.body,
        notification_type=request.type,
        priority=request.priority,
        target=request.target,
        channels=request.channels,
    )


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """通知を既読にする."""
    service = NotificationService(db)
    await service.mark_as_read(
        notification_id=notification_id,
        user_id=current_user.get("sub", ""),
    )
    return {"message": "既読にしました"}
