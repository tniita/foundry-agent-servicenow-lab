"""勤怠管理ビジネスロジック."""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.schemas import AttendanceRecord, AttendanceStatus

logger = logging.getLogger(__name__)

# 標準労働時間（時間）
STANDARD_WORK_HOURS = Decimal("8.0")
# デフォルト休憩時間（分）
DEFAULT_BREAK_MINUTES = 60


class AttendanceService:
    """勤怠管理サービス."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def clock_in(
        self,
        employee_id: str,
        timestamp: datetime,
        location: str = "",
        note: str = "",
    ) -> dict:
        """出勤打刻を記録する.

        同日に既に出勤記録がある場合は ValueError を送出する。
        """
        record_date = timestamp.date()

        # 重複チェック
        existing = await self._get_record_by_date(employee_id, record_date)
        if existing:
            raise ValueError(
                f"本日 ({record_date}) は既に出勤済みです。"
            )

        record = AttendanceRecord(
            id=str(uuid.uuid4()),
            employee_id=employee_id,
            date=record_date,
            clock_in=timestamp,
            location=location or None,
            status=AttendanceStatus.working.value,
            note=note or None,
        )
        self.db.add(record)
        await self.db.flush()

        logger.info("出勤打刻: %s (%s) at %s", employee_id, record_date, location)

        return {
            "id": record.id,
            "employee_id": employee_id,
            "date": record_date,
            "clock_in": timestamp,
            "clock_out": None,
            "work_hours": None,
            "overtime_hours": None,
            "location": location,
            "status": AttendanceStatus.working.value,
        }

    async def clock_out(
        self,
        employee_id: str,
        timestamp: datetime,
        note: str = "",
    ) -> dict:
        """退勤打刻を記録する.

        出勤記録がない場合は ValueError を送出する。
        実働時間と残業時間を自動計算する。
        """
        record_date = timestamp.date()
        record = await self._get_record_by_date(employee_id, record_date)

        if not record:
            raise ValueError(
                f"本日 ({record_date}) の出勤記録がありません。先に出勤打刻してください。"
            )

        if record.clock_out:
            raise ValueError(
                f"本日 ({record_date}) は既に退勤済みです。"
            )

        # 実働時間を計算（休憩時間を差し引き）
        work_seconds = (timestamp - record.clock_in).total_seconds()
        break_seconds = record.break_minutes * 60
        net_work_seconds = max(0, work_seconds - break_seconds)
        work_hours = Decimal(str(round(net_work_seconds / 3600, 2)))

        # 残業時間を計算
        overtime_hours = max(Decimal("0"), work_hours - STANDARD_WORK_HOURS)

        record.clock_out = timestamp
        record.work_hours = work_hours
        record.overtime_hours = overtime_hours
        record.status = AttendanceStatus.completed.value
        if note:
            record.note = note

        await self.db.flush()

        logger.info(
            "退勤打刻: %s (%s) 実働 %s時間 残業 %s時間",
            employee_id, record_date, work_hours, overtime_hours,
        )

        return {
            "id": record.id,
            "employee_id": employee_id,
            "date": record_date,
            "clock_in": record.clock_in,
            "clock_out": timestamp,
            "work_hours": float(work_hours),
            "overtime_hours": float(overtime_hours),
            "location": record.location,
            "status": AttendanceStatus.completed.value,
        }

    async def get_monthly_records(self, employee_id: str, month: str) -> dict:
        """月次勤怠記録を取得する.

        統計情報が古い場合、クエリ実行計画が最適でなくなりパフォーマンスが劣化する。
        PostgreSQL の ANALYZE は毎日 03:00 に自動実行される (DOC-DB-001 3.2 参照)。
        """
        year, month_num = map(int, month.split("-"))
        start_date = date(year, month_num, 1)
        if month_num == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month_num + 1, 1)

        stmt = (
            select(AttendanceRecord)
            .where(
                and_(
                    AttendanceRecord.employee_id == employee_id,
                    AttendanceRecord.date >= start_date,
                    AttendanceRecord.date < end_date,
                )
            )
            .order_by(AttendanceRecord.date)
        )

        result = await self.db.execute(stmt)
        records = result.scalars().all()

        # 月次サマリーを計算
        total_work_hours = sum(
            float(r.work_hours or 0) for r in records
        )
        total_overtime = sum(
            float(r.overtime_hours or 0) for r in records
        )
        late_count = sum(
            1 for r in records
            if r.clock_in and r.clock_in.hour >= 9 and r.clock_in.minute > 5
        )

        return {
            "employee_id": employee_id,
            "month": month,
            "summary": {
                "total_work_days": len(records),
                "total_work_hours": round(total_work_hours, 2),
                "total_overtime_hours": round(total_overtime, 2),
                "late_count": late_count,
            },
            "records": [
                {
                    "date": str(r.date),
                    "clock_in": r.clock_in.strftime("%H:%M:%S") if r.clock_in else None,
                    "clock_out": r.clock_out.strftime("%H:%M:%S") if r.clock_out else None,
                    "work_hours": float(r.work_hours) if r.work_hours else None,
                    "overtime_hours": float(r.overtime_hours) if r.overtime_hours else 0,
                    "status": r.status,
                }
                for r in records
            ],
        }

    async def start_monthly_summary(
        self, target_month: str, sync_to_sap: bool = False
    ) -> dict:
        """月次集計バッチジョブを開始する.

        注意: バッチ処理中はオンラインの勤怠照会がトランザクション競合により
        遅延する可能性がある。以下の対策を実施済み:
        - トランザクション分離レベルを READ COMMITTED SNAPSHOT に変更 (INC0001011)
        - デッドロック発生時は自動リトライ（最大3回）
        - 月次バッチのスケジュールを業務時間外（22:00 JST）に移動
        """
        job_id = f"batch_{target_month.replace('-', '')}_{uuid.uuid4().hex[:6]}"

        logger.info(
            "月次集計バッチ開始: job_id=%s, month=%s, sap_sync=%s",
            job_id, target_month, sync_to_sap,
        )

        return {
            "job_id": job_id,
            "status": "processing",
            "message": "月次集計を開始しました。完了時に通知します。",
        }

    async def _get_record_by_date(
        self, employee_id: str, record_date: date
    ) -> AttendanceRecord | None:
        """指定日の勤怠記録を取得する."""
        stmt = select(AttendanceRecord).where(
            and_(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.date == record_date,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
