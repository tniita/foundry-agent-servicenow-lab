"""経費精算ビジネスロジック."""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from azure.storage.blob import BlobServiceClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.schemas import (
    Approval,
    ExpenseItem,
    ExpenseItemCreate,
    ExpenseReport,
    ExpenseStatus,
)

logger = logging.getLogger(__name__)


class ExpenseService:
    """経費精算サービス."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_report(
        self,
        employee_id: str,
        title: str,
        description: str,
        items: list[ExpenseItemCreate],
    ) -> dict:
        """経費レポートをドラフト状態で作成する."""
        report_id = str(uuid.uuid4())
        total = sum(item.amount for item in items)

        report = ExpenseReport(
            id=report_id,
            employee_id=employee_id,
            title=title,
            description=description or None,
            total_amount=total,
            status=ExpenseStatus.draft.value,
        )
        self.db.add(report)

        for item in items:
            expense_item = ExpenseItem(
                id=str(uuid.uuid4()),
                report_id=report_id,
                category=item.category,
                amount=item.amount,
                date=item.date,
                description=item.description or None,
            )
            self.db.add(expense_item)

        await self.db.flush()

        logger.info("経費レポート作成: %s (合計: ¥%s)", report_id, total)

        return {
            "report_id": report_id,
            "status": ExpenseStatus.draft.value,
            "total_amount": float(total),
            "created_at": datetime.now(timezone.utc),
        }

    async def upload_receipt(
        self,
        report_id: str,
        file_name: str,
        content: bytes,
        content_type: str,
    ) -> dict:
        """領収書を Azure Blob Storage にアップロードする.

        Blob Storage への接続には Azure SDK を使用。
        CORS ポリシーの設定が必要 — CDN 経由の場合は特に注意 (INC0001006)。
        """
        receipt_id = str(uuid.uuid4())
        blob_name = f"{report_id}/{receipt_id}/{file_name}"

        try:
            blob_service = BlobServiceClient.from_connection_string(
                settings.blob_connection_string
            )
            blob_client = blob_service.get_blob_client(
                container=settings.blob_receipts_container,
                blob=blob_name,
            )
            blob_client.upload_blob(
                content,
                content_settings={"content_type": content_type},
                overwrite=True,
            )
            blob_url = blob_client.url
        except Exception as e:
            logger.error("領収書アップロード失敗: %s", str(e))
            raise

        logger.info("領収書アップロード: %s → %s", file_name, blob_url)

        return {
            "receipt_id": receipt_id,
            "file_name": file_name,
            "file_size": len(content),
            "blob_url": blob_url,
            "uploaded_at": datetime.now(timezone.utc),
        }

    async def submit_report(self, report_id: str, employee_id: str) -> dict:
        """経費レポートを承認フローに提出する."""
        report = await self._get_report(report_id)
        if not report:
            raise ValueError("指定された経費レポートが見つかりません。")

        if report.employee_id != employee_id:
            raise ValueError("他のユーザーの経費レポートは提出できません。")

        if report.status != ExpenseStatus.draft.value:
            raise ValueError(
                f"ドラフト状態のレポートのみ提出可能です (現在: {report.status})。"
            )

        report.status = ExpenseStatus.submitted.value
        report.submitted_at = datetime.now(timezone.utc)
        await self.db.flush()

        logger.info("経費レポート提出: %s", report_id)
        return {"report_id": report_id, "status": ExpenseStatus.submitted.value}

    async def approve_report(
        self,
        report_id: str,
        approver_id: str,
        action: str,
        comment: str = "",
    ) -> dict:
        """経費レポートを承認または却下する."""
        report = await self._get_report(report_id)
        if not report:
            raise ValueError("指定された経費レポートが見つかりません。")

        if report.status != ExpenseStatus.submitted.value:
            raise ValueError(
                f"提出済みのレポートのみ承認可能です (現在: {report.status})。"
            )

        valid_actions = {"approve", "reject", "return"}
        if action not in valid_actions:
            raise ValueError(f"無効なアクションです: {action}")

        # 承認履歴を記録
        approval = Approval(
            id=str(uuid.uuid4()),
            report_id=report_id,
            approver_id=approver_id,
            action=action,
            comment=comment or None,
        )
        self.db.add(approval)

        # レポートのステータスを更新
        status_map = {
            "approve": ExpenseStatus.approved.value,
            "reject": ExpenseStatus.rejected.value,
            "return": ExpenseStatus.draft.value,
        }
        report.status = status_map[action]
        await self.db.flush()

        logger.info("経費レポート %s: %s (承認者: %s)", action, report_id, approver_id)
        return {"report_id": report_id, "status": report.status, "action": action}

    async def _get_report(self, report_id: str) -> ExpenseReport | None:
        """経費レポートを取得する."""
        stmt = select(ExpenseReport).where(ExpenseReport.id == report_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
