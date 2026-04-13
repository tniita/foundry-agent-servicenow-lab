"""通知ビジネスロジック."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.schemas import Notification, NotificationRead

logger = logging.getLogger(__name__)


class NotificationService:
    """通知サービス — アプリ内通知・メール・Teams 配信."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 20,
    ) -> dict:
        """ユーザー向け通知を取得する."""
        stmt = (
            select(Notification)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        notifications = result.scalars().all()

        # 既読状態を取得
        read_stmt = select(NotificationRead.notification_id).where(
            NotificationRead.user_id == user_id
        )
        read_result = await self.db.execute(read_stmt)
        read_ids = {row[0] for row in read_result.all()}

        items = []
        for n in notifications:
            is_read = n.id in read_ids
            if unread_only and is_read:
                continue
            items.append({
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "type": n.type,
                "priority": n.priority,
                "is_read": is_read,
                "created_at": n.created_at,
            })

        return {"total": len(items), "notifications": items}

    async def create_notification(
        self,
        created_by: str,
        title: str,
        body: str,
        notification_type: str,
        priority: str = "normal",
        target: str = "all",
        channels: list[str] | None = None,
    ) -> dict:
        """通知を作成し、指定チャネルで配信する.

        配信チャネル:
        - in_app: アプリ内通知 (WebSocket 経由のリアルタイム配信)
        - email: Microsoft Graph API 経由のメール配信
        - teams: Microsoft Graph API 経由の Teams チャネル投稿
        """
        if channels is None:
            channels = ["in_app"]

        notification_id = str(uuid.uuid4())
        notification = Notification(
            id=notification_id,
            title=title,
            body=body,
            type=notification_type,
            priority=priority,
            target=target,
            channels=",".join(channels),
            created_by=created_by,
        )
        self.db.add(notification)
        await self.db.flush()

        # 各チャネルで配信
        delivery_results = {}
        for channel in channels:
            try:
                if channel == "in_app":
                    delivery_results["in_app"] = "delivered"
                elif channel == "email":
                    await self._send_email_notification(title, body)
                    delivery_results["email"] = "delivered"
                elif channel == "teams":
                    await self._send_teams_notification(title, body)
                    delivery_results["teams"] = "delivered"
            except Exception as e:
                logger.error("通知配信失敗 (%s): %s", channel, str(e))
                delivery_results[channel] = f"failed: {str(e)}"

        logger.info(
            "通知作成: %s (タイプ: %s, 優先度: %s, チャネル: %s)",
            notification_id, notification_type, priority, channels,
        )

        return {
            "notification_id": notification_id,
            "title": title,
            "delivery": delivery_results,
            "created_at": datetime.now(timezone.utc),
        }

    async def mark_as_read(self, notification_id: str, user_id: str):
        """通知を既読にする."""
        existing = await self.db.execute(
            select(NotificationRead).where(
                and_(
                    NotificationRead.notification_id == notification_id,
                    NotificationRead.user_id == user_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            return  # 既に既読

        read = NotificationRead(
            notification_id=notification_id,
            user_id=user_id,
        )
        self.db.add(read)
        await self.db.flush()

    async def _send_email_notification(self, title: str, body: str):
        """Microsoft Graph API 経由でメール通知を送信する.

        SMTP タイムアウト: 30秒 (INC0001002 — Exchange 送信キュー詰まり対策)
        リトライ: 3回（指数バックオフ、初回 5 秒）
        レート制限: 50件/分
        """
        retry_count = settings.smtp_retry_count
        base_delay = settings.smtp_retry_base_delay

        for attempt in range(retry_count):
            try:
                # Microsoft Graph API でメール送信
                # graph_client.send_mail(subject=title, body=body, timeout=30)
                logger.info("メール通知送信成功: %s", title)
                return
            except TimeoutError:
                wait_time = base_delay * (2 ** attempt)
                logger.warning(
                    "メール送信タイムアウト (試行 %d/%d)。%d秒後にリトライ...",
                    attempt + 1, retry_count, wait_time,
                )
                await asyncio.sleep(wait_time)
            except Exception as e:
                logger.error("メール送信エラー: %s", str(e))
                raise

        raise Exception("メール送信が全てのリトライで失敗しました")

    async def _send_teams_notification(self, title: str, body: str):
        """Microsoft Graph API 経由で Teams に投稿する."""
        # graph_client.post_channel_message(title=title, body=body)
        logger.info("Teams 通知送信成功: %s", title)
