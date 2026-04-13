# データベース設計書 — 社内業務ポータル (BizPortal)

| 項目 | 内容 |
|------|------|
| ドキュメント ID | DOC-DB-001 |
| バージョン | 1.5 |
| DBMS | PostgreSQL 15 (Azure Database for PostgreSQL Flexible Server) |
| 文字コード | UTF-8 |
| タイムゾーン | Asia/Tokyo (UTC+9) |

---

## 1. ER 図概要

```
┌──────────────┐     ┌────────────────────┐     ┌──────────────────┐
│   users      │────<│ attendance_records  │     │ notifications    │
│              │     └────────────────────┘     │                  │
│              │────<┌────────────────────┐     └────────┬─────────┘
│              │     │  leave_requests     │              │
│              │     └────────────────────┘     ┌────────▼─────────┐
│              │                                │notification_reads│
│              │────<┌────────────────────┐     └──────────────────┘
│              │     │  expense_reports    │
│              │     │       │             │
└──────────────┘     │       ├──< expense_items
                     │       │
                     │       └──< approvals
                     └────────────────────┘
```

---

## 2. テーブル定義

### 2.1 users（ユーザーマスタ）

Azure AD と同期するユーザー情報。

| カラム名 | 型 | NULL | デフォルト | 説明 |
|---------|-----|------|-----------|------|
| id | VARCHAR(36) | NO | UUID | 主キー |
| employee_id | VARCHAR(20) | NO | — | 社員番号（一意） |
| azure_ad_oid | VARCHAR(36) | NO | — | Azure AD Object ID |
| name | VARCHAR(100) | NO | — | 氏名 |
| email | VARCHAR(255) | NO | — | メールアドレス |
| department | VARCHAR(100) | YES | NULL | 部署名 |
| role | VARCHAR(20) | NO | 'employee' | ロール (admin/manager/employee) |
| is_active | BOOLEAN | NO | TRUE | アクティブフラグ |
| created_at | TIMESTAMPTZ | NO | NOW() | 作成日時 |
| updated_at | TIMESTAMPTZ | NO | NOW() | 更新日時 |

**インデックス:**
- `idx_users_employee_id` UNIQUE ON (employee_id)
- `idx_users_azure_ad_oid` UNIQUE ON (azure_ad_oid)
- `idx_users_email` UNIQUE ON (email)
- `idx_users_department` ON (department)

---

### 2.2 attendance_records（勤怠記録）

| カラム名 | 型 | NULL | デフォルト | 説明 |
|---------|-----|------|-----------|------|
| id | VARCHAR(36) | NO | UUID | 主キー |
| employee_id | VARCHAR(20) | NO | — | 社員番号 (FK: users.employee_id) |
| date | DATE | NO | — | 勤務日 |
| clock_in | TIMESTAMPTZ | YES | NULL | 出勤時刻 |
| clock_out | TIMESTAMPTZ | YES | NULL | 退勤時刻 |
| work_hours | DECIMAL(4,2) | YES | NULL | 実働時間 |
| overtime_hours | DECIMAL(4,2) | YES | 0 | 残業時間 |
| break_minutes | INTEGER | NO | 60 | 休憩時間（分） |
| location | VARCHAR(50) | YES | NULL | 勤務場所 |
| status | VARCHAR(20) | NO | 'working' | 状態 |
| note | TEXT | YES | NULL | 備考 |
| created_at | TIMESTAMPTZ | NO | NOW() | 作成日時 |
| updated_at | TIMESTAMPTZ | NO | NOW() | 更新日時 |

**status の取りうる値:** `working`, `completed`, `modified`, `approved`

**インデックス:**
- `idx_attendance_employee_date` UNIQUE ON (employee_id, date)
- `idx_attendance_date` ON (date)
- `idx_attendance_status` ON (status)

**制約:**
- `clock_out` は `clock_in` より後であること
- `work_hours` は 0 以上 24 以下
- `overtime_hours` は 0 以上

---

### 2.3 leave_requests（休暇申請）

| カラム名 | 型 | NULL | デフォルト | 説明 |
|---------|-----|------|-----------|------|
| id | VARCHAR(36) | NO | UUID | 主キー |
| employee_id | VARCHAR(20) | NO | — | 社員番号 |
| leave_type | VARCHAR(20) | NO | — | 休暇種別 |
| start_date | DATE | NO | — | 開始日 |
| end_date | DATE | NO | — | 終了日 |
| days | DECIMAL(3,1) | NO | — | 日数（0.5日単位） |
| reason | TEXT | YES | NULL | 理由 |
| status | VARCHAR(20) | NO | 'pending' | 承認状態 |
| approved_by | VARCHAR(36) | YES | NULL | 承認者 ID |
| approved_at | TIMESTAMPTZ | YES | NULL | 承認日時 |
| created_at | TIMESTAMPTZ | NO | NOW() | 作成日時 |

**leave_type:** `paid`, `sick`, `special`, `unpaid`
**status:** `pending`, `approved`, `rejected`, `cancelled`

---

### 2.4 expense_reports（経費レポート）

| カラム名 | 型 | NULL | デフォルト | 説明 |
|---------|-----|------|-----------|------|
| id | VARCHAR(36) | NO | UUID | 主キー |
| employee_id | VARCHAR(20) | NO | — | 申請者社員番号 |
| title | VARCHAR(200) | NO | — | レポートタイトル |
| description | TEXT | YES | NULL | 説明 |
| total_amount | DECIMAL(12,2) | NO | 0 | 合計金額 |
| currency | VARCHAR(3) | NO | 'JPY' | 通貨コード |
| status | VARCHAR(20) | NO | 'draft' | 承認状態 |
| submitted_at | TIMESTAMPTZ | YES | NULL | 提出日時 |
| created_at | TIMESTAMPTZ | NO | NOW() | 作成日時 |
| updated_at | TIMESTAMPTZ | NO | NOW() | 更新日時 |

**status:** `draft`, `submitted`, `approved`, `rejected`, `paid`

---

### 2.5 expense_items（経費明細）

| カラム名 | 型 | NULL | デフォルト | 説明 |
|---------|-----|------|-----------|------|
| id | VARCHAR(36) | NO | UUID | 主キー |
| report_id | VARCHAR(36) | NO | — | レポート ID (FK) |
| category | VARCHAR(50) | NO | — | 費目カテゴリ |
| amount | DECIMAL(12,2) | NO | — | 金額 |
| date | DATE | NO | — | 発生日 |
| description | VARCHAR(500) | YES | NULL | 内容説明 |
| receipt_url | VARCHAR(500) | YES | NULL | 領収書 Blob URL |
| created_at | TIMESTAMPTZ | NO | NOW() | 作成日時 |

**category の値:** `交通費`, `宿泊費`, `飲食費`, `通信費`, `消耗品費`, `その他`

---

### 2.6 approvals（承認履歴）

| カラム名 | 型 | NULL | デフォルト | 説明 |
|---------|-----|------|-----------|------|
| id | VARCHAR(36) | NO | UUID | 主キー |
| report_id | VARCHAR(36) | NO | — | レポート ID (FK) |
| approver_id | VARCHAR(36) | NO | — | 承認者 ID (FK: users.id) |
| action | VARCHAR(20) | NO | — | アクション |
| comment | TEXT | YES | NULL | コメント |
| acted_at | TIMESTAMPTZ | NO | NOW() | 実行日時 |

**action:** `approve`, `reject`, `return`

---

### 2.7 notifications（通知）

| カラム名 | 型 | NULL | デフォルト | 説明 |
|---------|-----|------|-----------|------|
| id | VARCHAR(36) | NO | UUID | 主キー |
| title | VARCHAR(200) | NO | — | 通知タイトル |
| body | TEXT | NO | — | 通知本文 |
| type | VARCHAR(50) | NO | — | 通知種別 |
| priority | VARCHAR(10) | NO | 'normal' | 優先度 (low/normal/high/urgent) |
| target | VARCHAR(20) | NO | 'all' | 配信対象 (all/department/individual) |
| target_value | VARCHAR(100) | YES | NULL | 対象値（部署名 or ユーザーID） |
| channels | VARCHAR(100) | NO | 'in_app' | 配信チャネル (カンマ区切り) |
| created_by | VARCHAR(36) | NO | — | 作成者 ID |
| created_at | TIMESTAMPTZ | NO | NOW() | 作成日時 |
| expires_at | TIMESTAMPTZ | YES | NULL | 有効期限 |

---

### 2.8 notification_reads（既読管理）

| カラム名 | 型 | NULL | デフォルト | 説明 |
|---------|-----|------|-----------|------|
| notification_id | VARCHAR(36) | NO | — | 通知 ID (FK, PK) |
| user_id | VARCHAR(36) | NO | — | ユーザー ID (FK, PK) |
| read_at | TIMESTAMPTZ | NO | NOW() | 既読日時 |

**主キー:** (notification_id, user_id)

---

## 3. パフォーマンス設計

### 3.1 接続プール設定

```
max_connections = 100
connection_pool_size = 20 (アプリケーション側 SQLAlchemy)
connection_pool_max_overflow = 10
connection_pool_timeout = 30
```

**注意:** 接続プールの使用率が 80% を超えた場合、Azure Monitor でアラートを発報する設定済み。

### 3.2 統計情報管理

- PostgreSQL の ANALYZE は毎日 03:00 に自動実行
- 大量データ変更後は手動で `ANALYZE` を実行すること
- 統計情報が古いとクエリプランが最適でなくなり性能劣化する（INC0001004 参考：SAP でも同様事象が発生）

### 3.3 トランザクション分離レベル

- デフォルト: `READ COMMITTED`
- 月次バッチ処理: `READ COMMITTED` + `SNAPSHOT ISOLATION` で MVCC 活用
- デッドロック発生時は自動リトライ（最大 3 回）

### 3.4 パーティショニング

`attendance_records` テーブルは月次レンジパーティションを適用:

```sql
CREATE TABLE attendance_records (
    ...
) PARTITION BY RANGE (date);

CREATE TABLE attendance_records_2025_01 PARTITION OF attendance_records
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

---

## 4. データ文字コードに関する注意

- データベースの文字コードは **必ず UTF-8** を使用すること
- システムアップデートやマイグレーション時に文字コードが変更されないよう確認手順を必ず実施
- 文字化けが発生した場合は `pg_encoding_to_char()` で現在のエンコーディングを確認
- 参考: INC0001016 で CRM システムにて文字コード設定の意図しない変更により文字化けが発生した事例あり

---

## 5. バックアップ・リストア

| 項目 | 設定 |
|------|------|
| 自動バックアップ | Azure PITR (ポイントインタイムリストア) |
| バックアップ保持期間 | 35 日 |
| バックアップストレージ | ゾーン冗長 (ZRS) |
| 手動バックアップ | pg_dump による論理バックアップ（週次） |
| バックアップ先容量監視 | 使用率 80% でアラート（INC0001009 の教訓より） |
