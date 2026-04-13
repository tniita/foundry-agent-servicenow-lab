"""経費精算 API エンドポイント."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.models.database import get_db
from src.models.schemas import ExpenseReportCreate, ExpenseReportResponse
from src.expense.service import ExpenseService

router = APIRouter()


@router.post("/reports", response_model=ExpenseReportResponse, status_code=201)
async def create_expense_report(
    request: ExpenseReportCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """経費レポート作成.

    明細項目を含む経費レポートをドラフト状態で作成する。
    """
    service = ExpenseService(db)
    report = await service.create_report(
        employee_id=current_user.get("employee_id", ""),
        title=request.title,
        description=request.description,
        items=request.items,
    )
    return report


@router.post("/reports/{report_id}/receipts", status_code=201)
async def upload_receipt(
    report_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """領収書アップロード.

    JPG/PNG/PDF ファイルを Azure Blob Storage にアップロードし、経費明細に紐付ける。
    最大ファイルサイズ: 10MB。

    CORS 設定に関する注意:
    CDN 経由のアップロードでは CORS ポリシーが必要。デプロイ時に CORS 設定が
    欠落するとアップロードが失敗する (INC0001006 参考)。
    """
    # ファイルサイズチェック (10MB上限)
    content = await file.read()
    max_size = 10 * 1024 * 1024  # 10MB
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"ファイルサイズが上限（10MB）を超えています。",
        )

    # ファイル形式チェック
    allowed_types = {"image/jpeg", "image/png", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"許可されていないファイル形式です。対応形式: JPG, PNG, PDF",
        )

    service = ExpenseService(db)
    receipt = await service.upload_receipt(
        report_id=report_id,
        file_name=file.filename or "receipt",
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )
    return receipt


@router.post("/reports/{report_id}/submit")
async def submit_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """経費レポート提出.

    ドラフト状態のレポートを承認フローに提出する。
    """
    service = ExpenseService(db)
    try:
        return await service.submit_report(
            report_id=report_id,
            employee_id=current_user.get("employee_id", ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/reports/{report_id}/approve")
async def approve_report(
    report_id: str,
    action: str = "approve",
    comment: str = "",
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """経費レポート承認/却下.

    manager 以上の権限が必要。
    """
    user_role = current_user.get("role", "employee")
    if user_role == "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="経費レポートの承認には manager 以上の権限が必要です。",
        )

    service = ExpenseService(db)
    try:
        return await service.approve_report(
            report_id=report_id,
            approver_id=current_user.get("sub", ""),
            action=action,
            comment=comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
