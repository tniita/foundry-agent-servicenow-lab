"""勤怠管理 API エンドポイント."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.models.database import get_db
from src.models.schemas import (
    AttendanceResponse,
    ClockInRequest,
    ClockOutRequest,
    MonthlySummaryRequest,
)
from src.attendance.service import AttendanceService

router = APIRouter()


@router.post("/clock-in", response_model=AttendanceResponse, status_code=201)
async def clock_in(
    request: ClockInRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """出勤打刻.

    同日に既に出勤済みの場合は 400 エラーを返す。
    """
    service = AttendanceService(db)
    try:
        record = await service.clock_in(
            employee_id=current_user.get("employee_id", ""),
            timestamp=request.timestamp,
            location=request.location,
            note=request.note,
        )
        return record
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/clock-out", response_model=AttendanceResponse)
async def clock_out(
    request: ClockOutRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """退勤打刻.

    出勤記録がない場合は 404 エラーを返す。
    """
    service = AttendanceService(db)
    try:
        record = await service.clock_out(
            employee_id=current_user.get("employee_id", ""),
            timestamp=request.timestamp,
            note=request.note,
        )
        return record
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("")
async def get_attendance_records(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="対象月 (YYYY-MM)"),
    employee_id: str | None = Query(None, description="社員番号（管理者のみ他者指定可）"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """勤怠記録取得.

    月単位で勤怠記録を取得する。一般ユーザーは自身のみ閲覧可能。
    manager は部下の勤怠を閲覧可能。admin は全員の勤怠を閲覧可能。
    """
    service = AttendanceService(db)
    target_employee_id = employee_id or current_user.get("employee_id", "")

    # 権限チェック: 他者の勤怠は manager 以上のみ
    if target_employee_id != current_user.get("employee_id"):
        user_role = current_user.get("role", "employee")
        if user_role == "employee":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="他の社員の勤怠記録を閲覧する権限がありません。",
            )

    return await service.get_monthly_records(target_employee_id, month)


@router.post("/monthly-summary", status_code=202)
async def run_monthly_summary(
    request: MonthlySummaryRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """月次集計バッチ実行 (admin のみ).

    全従業員の月次勤怠を集計する。バッチ処理中はオンラインの勤怠照会が
    トランザクション競合により遅延する可能性あり。
    READ COMMITTED SNAPSHOT 分離レベルで競合を最小化 (INC0001011 対応済み)。
    バッチ実行は業務時間外（22:00 JST 以降）を推奨。
    """
    user_role = current_user.get("role", "employee")
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="月次集計は管理者のみ実行可能です。",
        )

    service = AttendanceService(db)
    job = await service.start_monthly_summary(
        target_month=request.target_month,
        sync_to_sap=request.sync_to_sap,
    )
    return job
