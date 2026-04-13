# API 仕様書 — 社内業務ポータル (BizPortal)

| 項目 | 内容 |
|------|------|
| ドキュメント ID | DOC-API-001 |
| バージョン | 2.0 |
| ベース URL | `https://bizportal-api.example.co.jp/api/v1` |
| 認証方式 | Bearer Token (JWT) |

---

## 1. 共通仕様

### 1.1 認証ヘッダー

```
Authorization: Bearer <JWT_TOKEN>
```

### 1.2 エラーレスポンス形式

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "入力値が不正です",
    "details": [
      { "field": "date", "message": "日付形式が不正です (YYYY-MM-DD)" }
    ]
  }
}
```

### 1.3 共通エラーコード

| HTTP | コード | 説明 |
|------|--------|------|
| 400 | VALIDATION_ERROR | リクエストパラメータ不正 |
| 401 | UNAUTHORIZED | 認証トークン無効・期限切れ |
| 403 | FORBIDDEN | 権限不足 |
| 404 | NOT_FOUND | リソースが存在しない |
| 429 | RATE_LIMITED | レート制限超過（100 req/min） |
| 500 | INTERNAL_ERROR | サーバー内部エラー |

---

## 2. 認証 API (`/auth`)

### 2.1 Azure AD ログイン

```
POST /auth/login
```

Azure AD から取得した認証コードを使ってシステム内 JWT を発行する。

**リクエスト:**
```json
{
  "authorization_code": "0.AXYA...",
  "redirect_uri": "https://bizportal.example.co.jp/callback"
}
```

**レスポンス (200):**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZn...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": {
    "id": "usr_001",
    "employee_id": "EMP-2024-0001",
    "name": "田中 太郎",
    "email": "tanaka@example.co.jp",
    "department": "情報システム部",
    "role": "admin"
  }
}
```

### 2.2 トークンリフレッシュ

```
POST /auth/refresh
```

**リクエスト:**
```json
{
  "refresh_token": "dGhpcyBpcyBhIHJlZn..."
}
```

**レスポンス (200):**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "expires_in": 3600
}
```

### 2.3 ログアウト

```
POST /auth/logout
```

現在のセッションを無効化し、リフレッシュトークンをリボークする。

**レスポンス (200):**
```json
{ "message": "ログアウトしました" }
```

---

## 3. 勤怠管理 API (`/attendance`)

### 3.1 出勤打刻

```
POST /attendance/clock-in
```

**リクエスト:**
```json
{
  "timestamp": "2025-03-15T09:00:00+09:00",
  "location": "本社オフィス",
  "note": ""
}
```

**レスポンス (201):**
```json
{
  "id": "att_20250315_001",
  "employee_id": "EMP-2024-0001",
  "clock_in": "2025-03-15T09:00:00+09:00",
  "clock_out": null,
  "location": "本社オフィス",
  "status": "working"
}
```

### 3.2 退勤打刻

```
POST /attendance/clock-out
```

**リクエスト:**
```json
{
  "timestamp": "2025-03-15T18:00:00+09:00",
  "note": ""
}
```

**レスポンス (200):**
```json
{
  "id": "att_20250315_001",
  "employee_id": "EMP-2024-0001",
  "clock_in": "2025-03-15T09:00:00+09:00",
  "clock_out": "2025-03-15T18:00:00+09:00",
  "work_hours": 8.0,
  "overtime_hours": 0.0,
  "status": "completed"
}
```

### 3.3 勤怠記録取得

```
GET /attendance?month=2025-03&employee_id=EMP-2024-0001
```

**レスポンス (200):**
```json
{
  "employee_id": "EMP-2024-0001",
  "month": "2025-03",
  "summary": {
    "total_work_days": 20,
    "total_work_hours": 165.5,
    "total_overtime_hours": 5.5,
    "late_count": 1,
    "paid_leave_used": 1
  },
  "records": [
    {
      "date": "2025-03-01",
      "clock_in": "09:02:00",
      "clock_out": "18:00:00",
      "work_hours": 7.97,
      "overtime_hours": 0,
      "status": "completed"
    }
  ]
}
```

### 3.4 月次集計バッチ実行

```
POST /attendance/monthly-summary
```

管理者のみ実行可能。全従業員の月次勤怠を集計して SAP に連携する。

**リクエスト:**
```json
{
  "target_month": "2025-03",
  "sync_to_sap": true
}
```

**レスポンス (202):**
```json
{
  "job_id": "batch_202503_001",
  "status": "processing",
  "message": "月次集計を開始しました。完了時に通知します。"
}
```

**注意事項:**
- バッチ処理中はオンラインの勤怠照会がトランザクション競合により遅延する可能性あり
- `READ COMMITTED SNAPSHOT` 分離レベルで競合を最小化（2025-02-28 のインシデント INC0001011 対応で適用済み）
- バッチ実行は業務時間外（22:00 JST 以降）を推奨

---

## 4. 経費精算 API (`/expense`)

### 4.1 経費レポート作成

```
POST /expense/reports
```

**リクエスト:**
```json
{
  "title": "2025年3月出張経費",
  "description": "東京→大阪 顧客訪問",
  "items": [
    {
      "category": "交通費",
      "amount": 14000,
      "currency": "JPY",
      "date": "2025-03-10",
      "description": "東京-大阪 新幹線往復"
    },
    {
      "category": "宿泊費",
      "amount": 12000,
      "currency": "JPY",
      "date": "2025-03-10",
      "description": "大阪ビジネスホテル1泊"
    }
  ]
}
```

**レスポンス (201):**
```json
{
  "report_id": "exp_20250310_001",
  "status": "draft",
  "total_amount": 26000,
  "created_at": "2025-03-15T10:00:00+09:00"
}
```

### 4.2 領収書アップロード

```
POST /expense/reports/{report_id}/receipts
Content-Type: multipart/form-data
```

**パラメータ:**
- `file`: 領収書画像ファイル (JPG/PNG/PDF, 最大 10MB)
- `item_id`: 紐付ける経費項目 ID

**レスポンス (201):**
```json
{
  "receipt_id": "rcpt_001",
  "file_name": "receipt_shinkansen.jpg",
  "file_size": 245000,
  "blob_url": "https://bizportalstore.blob.core.windows.net/receipts/...",
  "uploaded_at": "2025-03-15T10:05:00+09:00"
}
```

**CORS 設定に関する注意:**
- CDN 経由のアップロードでは CORS ポリシーが必要
- `Access-Control-Allow-Origin` に `https://bizportal.example.co.jp` を許可
- デプロイ時に CORS 設定が欠落しないよう CI パイプラインでチェック（INC0001006 対応）

### 4.3 経費レポート承認

```
POST /expense/reports/{report_id}/approve
```

承認者のみ実行可能。

**リクエスト:**
```json
{
  "action": "approve",
  "comment": "内容確認済み。承認します。"
}
```

---

## 5. 通知 API (`/notifications`)

### 5.1 通知一覧取得

```
GET /notifications?unread_only=true&limit=20
```

**レスポンス (200):**
```json
{
  "total": 5,
  "notifications": [
    {
      "id": "ntf_001",
      "title": "経費レポートが承認されました",
      "body": "2025年3月出張経費が承認されました。",
      "type": "expense_approved",
      "priority": "normal",
      "is_read": false,
      "created_at": "2025-03-16T09:00:00+09:00"
    }
  ]
}
```

### 5.2 通知作成（管理者向け）

```
POST /notifications
```

**リクエスト:**
```json
{
  "title": "システムメンテナンスのお知らせ",
  "body": "4月12日(土) 02:00-06:00 にシステムメンテナンスを実施します。",
  "type": "system_maintenance",
  "priority": "high",
  "target": "all",
  "channels": ["in_app", "email", "teams"]
}
```

**配信チャネル:**
| チャネル | 説明 | 実装 |
|---------|------|------|
| `in_app` | アプリ内通知バッジ | WebSocket (リアルタイム) |
| `email` | メール送信 | Microsoft Graph API (Exchange Online) |
| `teams` | Teams チャネル投稿 | Microsoft Graph API (Teams) |

**メール送信時の注意事項:**
- SMTP タイムアウトは 30 秒に設定（Exchange の送信キュー詰まり対策、INC0001002 参考）
- 送信失敗時は 3 回リトライ（指数バックオフ、初回 5 秒）
- 大量配信は 50 件/分にレート制限

### 5.3 既読マーク

```
POST /notifications/{notification_id}/read
```

---

## 6. ヘルスチェック API

### 6.1 ヘルスチェック

```
GET /health
```

**レスポンス (200):**
```json
{
  "status": "healthy",
  "version": "2.1.0",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "blob_storage": "ok",
    "azure_ad": "ok"
  },
  "timestamp": "2025-03-15T12:00:00+09:00"
}
```

**注意:** ヘルスチェックエンドポイントは Azure App Service のヘルスチェック設定から呼び出される。
App Service Plan のスケールイン時に最小インスタンス数を 1 以上に設定すること（INC0001018 の教訓）。
