"""勤怠管理モジュールのユニットテスト."""

import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.attendance.service import AttendanceService, STANDARD_WORK_HOURS
from src.models.schemas import AttendanceRecord, AttendanceStatus


class TestClockIn:
    """出勤打刻のテスト."""

    @pytest.mark.asyncio
    async def test_clock_in_success(self):
        """正常系: 出勤打刻が成功する."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        service = AttendanceService(mock_db)
        result = await service.clock_in(
            employee_id="EMP-2024-0001",
            timestamp=datetime(2025, 3, 15, 9, 0, 0, tzinfo=timezone.utc),
            location="本社オフィス",
        )

        assert result["employee_id"] == "EMP-2024-0001"
        assert result["status"] == AttendanceStatus.working.value
        assert result["location"] == "本社オフィス"
        assert result["clock_out"] is None

    @pytest.mark.asyncio
    async def test_clock_in_duplicate_raises_error(self):
        """異常系: 同日に二重出勤するとエラー."""
        existing_record = AttendanceRecord(
            id=str(uuid.uuid4()),
            employee_id="EMP-2024-0001",
            date=date(2025, 3, 15),
            status=AttendanceStatus.working.value,
        )
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=existing_record)
            )
        )

        service = AttendanceService(mock_db)
        with pytest.raises(ValueError, match="既に出勤済み"):
            await service.clock_in(
                employee_id="EMP-2024-0001",
                timestamp=datetime(2025, 3, 15, 9, 30, 0, tzinfo=timezone.utc),
            )


class TestClockOut:
    """退勤打刻のテスト."""

    @pytest.mark.asyncio
    async def test_clock_out_calculates_hours(self):
        """正常系: 退勤打刻で実働時間と残業時間が計算される."""
        clock_in_time = datetime(2025, 3, 15, 9, 0, 0, tzinfo=timezone.utc)
        existing_record = AttendanceRecord(
            id=str(uuid.uuid4()),
            employee_id="EMP-2024-0001",
            date=date(2025, 3, 15),
            clock_in=clock_in_time,
            clock_out=None,
            break_minutes=60,
            status=AttendanceStatus.working.value,
        )
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=existing_record)
            )
        )

        service = AttendanceService(mock_db)
        clock_out_time = datetime(2025, 3, 15, 18, 0, 0, tzinfo=timezone.utc)
        result = await service.clock_out(
            employee_id="EMP-2024-0001",
            timestamp=clock_out_time,
        )

        assert result["status"] == AttendanceStatus.completed.value
        assert result["work_hours"] == 8.0  # 9時間 - 1時間休憩
        assert result["overtime_hours"] == 0.0

    @pytest.mark.asyncio
    async def test_clock_out_with_overtime(self):
        """正常系: 残業ありの退勤打刻."""
        clock_in_time = datetime(2025, 3, 15, 9, 0, 0, tzinfo=timezone.utc)
        existing_record = AttendanceRecord(
            id=str(uuid.uuid4()),
            employee_id="EMP-2024-0001",
            date=date(2025, 3, 15),
            clock_in=clock_in_time,
            clock_out=None,
            break_minutes=60,
            status=AttendanceStatus.working.value,
        )
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=existing_record)
            )
        )

        service = AttendanceService(mock_db)
        # 21:00 退勤 → 実働 11時間、残業 3時間
        clock_out_time = datetime(2025, 3, 15, 21, 0, 0, tzinfo=timezone.utc)
        result = await service.clock_out(
            employee_id="EMP-2024-0001",
            timestamp=clock_out_time,
        )

        assert result["work_hours"] == 11.0
        assert result["overtime_hours"] == 3.0

    @pytest.mark.asyncio
    async def test_clock_out_without_clock_in_raises_error(self):
        """異常系: 出勤記録なしで退勤するとエラー."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        service = AttendanceService(mock_db)
        with pytest.raises(ValueError, match="出勤記録がありません"):
            await service.clock_out(
                employee_id="EMP-2024-0001",
                timestamp=datetime(2025, 3, 15, 18, 0, 0, tzinfo=timezone.utc),
            )


class TestMonthlySummary:
    """月次集計のテスト."""

    @pytest.mark.asyncio
    async def test_start_monthly_summary_returns_job(self):
        """正常系: 月次集計バッチが開始される."""
        mock_db = AsyncMock()
        service = AttendanceService(mock_db)

        result = await service.start_monthly_summary(
            target_month="2025-03",
            sync_to_sap=True,
        )

        assert result["status"] == "processing"
        assert "job_id" in result
        assert "batch_202503" in result["job_id"]
