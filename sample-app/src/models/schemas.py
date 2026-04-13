"""SQLAlchemy モデル & Pydantic スキーマ定義."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

from src.models.database import Base


# ──────────────────────────────────────────────
# Enum 定義
# ──────────────────────────────────────────────

class UserRole(str, Enum):
    admin = "admin"
    manager = "manager"
    employee = "employee"


class AttendanceStatus(str, Enum):
    working = "working"
    completed = "completed"
    modified = "modified"
    approved = "approved"


class LeaveType(str, Enum):
    paid = "paid"
    sick = "sick"
    special = "special"
    unpaid = "unpaid"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class ExpenseStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    paid = "paid"


class NotificationPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


# ──────────────────────────────────────────────
# SQLAlchemy ORM モデル
# ──────────────────────────────────────────────

def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """ユーザーマスタ — Azure AD と同期."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    employee_id = Column(String(20), unique=True, nullable=False, index=True)
    azure_ad_oid = Column(String(36), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    department = Column(String(100), nullable=True, index=True)
    role = Column(String(20), nullable=False, default=UserRole.employee.value)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    attendance_records = relationship("AttendanceRecord", back_populates="user")
    expense_reports = relationship("ExpenseReport", back_populates="user")


class AttendanceRecord(Base):
    """勤怠記録 — 月次レンジパーティション適用 (DOC-DB-001 3.4)."""
    __tablename__ = "attendance_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    employee_id = Column(String(20), ForeignKey("users.employee_id"), nullable=False)
    date = Column(Date, nullable=False)
    clock_in = Column(DateTime(timezone=True), nullable=True)
    clock_out = Column(DateTime(timezone=True), nullable=True)
    work_hours = Column(Numeric(4, 2), nullable=True)
    overtime_hours = Column(Numeric(4, 2), nullable=True, default=0)
    break_minutes = Column(Integer, nullable=False, default=60)
    location = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default=AttendanceStatus.working.value)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
        Index("idx_attendance_date", "date"),
        Index("idx_attendance_status", "status"),
    )

    user = relationship("User", back_populates="attendance_records")


class LeaveRequest(Base):
    """休暇申請."""
    __tablename__ = "leave_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    employee_id = Column(String(20), ForeignKey("users.employee_id"), nullable=False)
    leave_type = Column(String(20), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Numeric(3, 1), nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default=ApprovalStatus.pending.value)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ExpenseReport(Base):
    """経費レポート."""
    __tablename__ = "expense_reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    employee_id = Column(String(20), ForeignKey("users.employee_id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="JPY")
    status = Column(String(20), nullable=False, default=ExpenseStatus.draft.value)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="expense_reports")
    items = relationship("ExpenseItem", back_populates="report", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="report")


class ExpenseItem(Base):
    """経費明細."""
    __tablename__ = "expense_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    report_id = Column(String(36), ForeignKey("expense_reports.id"), nullable=False)
    category = Column(String(50), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    date = Column(Date, nullable=False)
    description = Column(String(500), nullable=True)
    receipt_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    report = relationship("ExpenseReport", back_populates="items")


class Approval(Base):
    """承認履歴."""
    __tablename__ = "approvals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    report_id = Column(String(36), ForeignKey("expense_reports.id"), nullable=False)
    approver_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    action = Column(String(20), nullable=False)
    comment = Column(Text, nullable=True)
    acted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    report = relationship("ExpenseReport", back_populates="approvals")


class Notification(Base):
    """通知."""
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)
    priority = Column(String(10), nullable=False, default=NotificationPriority.normal.value)
    target = Column(String(20), nullable=False, default="all")
    target_value = Column(String(100), nullable=True)
    channels = Column(String(100), nullable=False, default="in_app")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)

    reads = relationship("NotificationRead", back_populates="notification")


class NotificationRead(Base):
    """通知既読管理."""
    __tablename__ = "notification_reads"

    notification_id = Column(String(36), ForeignKey("notifications.id"), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    read_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    notification = relationship("Notification", back_populates="reads")


# ──────────────────────────────────────────────
# Pydantic スキーマ (API リクエスト/レスポンス)
# ──────────────────────────────────────────────

class ClockInRequest(BaseModel):
    """出勤打刻リクエスト."""
    timestamp: datetime
    location: str = ""
    note: str = ""


class ClockOutRequest(BaseModel):
    """退勤打刻リクエスト."""
    timestamp: datetime
    note: str = ""


class AttendanceResponse(BaseModel):
    """勤怠記録レスポンス."""
    id: str
    employee_id: str
    date: date
    clock_in: datetime | None
    clock_out: datetime | None
    work_hours: float | None
    overtime_hours: float | None
    location: str | None
    status: str


class MonthlySummaryRequest(BaseModel):
    """月次集計リクエスト."""
    target_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    sync_to_sap: bool = False


class ExpenseItemCreate(BaseModel):
    """経費明細作成リクエスト."""
    category: str
    amount: Decimal
    date: date
    description: str = ""


class ExpenseReportCreate(BaseModel):
    """経費レポート作成リクエスト."""
    title: str
    description: str = ""
    items: list[ExpenseItemCreate]


class ExpenseReportResponse(BaseModel):
    """経費レポートレスポンス."""
    report_id: str
    status: str
    total_amount: float
    created_at: datetime


class NotificationCreate(BaseModel):
    """通知作成リクエスト."""
    title: str
    body: str
    type: str
    priority: str = "normal"
    target: str = "all"
    channels: list[str] = ["in_app"]


class NotificationResponse(BaseModel):
    """通知レスポンス."""
    id: str
    title: str
    body: str
    type: str
    priority: str
    is_read: bool
    created_at: datetime
