# セキュリティ設計書 — 社内業務ポータル (BizPortal)

| 項目 | 内容 |
|------|------|
| ドキュメント ID | DOC-SEC-001 |
| バージョン | 1.4 |
| セキュリティレベル | 社外秘 |
| 最終更新日 | 2025-03-16 |

---

## 1. 認証・認可設計

### 1.1 認証方式

Azure Active Directory (Azure AD) を ID プロバイダーとして使用し、OAuth 2.0 / OpenID Connect による SSO を実現する。

```
ユーザー → Azure AD (認証) → 認可コード → BizPortal API → JWT 発行
```

**フロー詳細:**

1. フロントエンドが Azure AD の `/authorize` エンドポイントにリダイレクト
2. ユーザーが Azure AD で認証（パスワード + MFA）
3. Azure AD が認可コードをコールバック URL に返却
4. バックエンドが認可コードを Azure AD の `/token` エンドポイントに送信
5. ID トークン + アクセストークンを受領
6. バックエンドがシステム内 JWT を発行してフロントエンドに返却

### 1.2 多要素認証 (MFA)

- Azure AD の条件付きアクセスポリシーにより MFA を強制
- 認証方式: Microsoft Authenticator アプリ（推奨）/ SMS
- SMS 認証の場合、SMS プロバイダー（Twilio）の API キー有効期限を四半期ごとに確認すること
- 参考: INC0001010 で Twilio API キー期限切れにより SMS 認証が全停止した事例あり

### 1.3 JWT 仕様

| 項目 | 値 |
|------|-----|
| アルゴリズム | RS256 |
| 有効期間 | 1 時間 |
| リフレッシュトークン有効期間 | 7 日 |
| 発行者 (iss) | https://bizportal-api.example.co.jp |
| 署名鍵 | Azure Key Vault に保管 |

**JWT ペイロード:**

```json
{
  "sub": "usr_001",
  "employee_id": "EMP-2024-0001",
  "name": "田中 太郎",
  "email": "tanaka@example.co.jp",
  "department": "情報システム部",
  "role": "admin",
  "iat": 1710489600,
  "exp": 1710493200,
  "iss": "https://bizportal-api.example.co.jp"
}
```

### 1.4 ロールベースアクセス制御 (RBAC)

| ロール | 権限 |
|--------|------|
| admin | 全機能のフルアクセス、システム設定変更、ユーザー管理 |
| manager | 部下の勤怠・経費の承認、部門レポート閲覧 |
| employee | 自身の勤怠打刻・経費申請・通知閲覧 |

**API エンドポイントごとの権限マトリクス:**

| エンドポイント | admin | manager | employee |
|--------------|-------|---------|----------|
| POST /attendance/clock-in | ✅ | ✅ | ✅ |
| GET /attendance (他者) | ✅ | ✅ (部下のみ) | ❌ |
| POST /attendance/monthly-summary | ✅ | ❌ | ❌ |
| POST /expense/reports | ✅ | ✅ | ✅ |
| POST /expense/reports/{id}/approve | ✅ | ✅ | ❌ |
| POST /notifications (作成) | ✅ | ✅ | ❌ |
| GET /notifications | ✅ | ✅ | ✅ |

---

## 2. 通信セキュリティ

### 2.1 TLS 設定

- 全通信は TLS 1.3 を使用
- TLS 1.0 / 1.1 は無効化済み
- 証明書は Azure Key Vault で管理し自動ローテーション
- HSTS ヘッダー: `max-age=31536000; includeSubDomains; preload`

### 2.2 CORS 設定

許可オリジン:
- `https://bizportal.example.co.jp` (本番)
- `https://bizportal-stg.example.co.jp` (ステージング)

**注意:** CORS 設定の欠落により経費精算システムのファイルアップロードが失敗する事象が過去に発生。デプロイパイプラインに CORS 設定の自動チェックを追加済み（INC0001006）。

---

## 3. データ保護

### 3.1 保存時の暗号化

| データ | 暗号化方式 |
|--------|-----------|
| PostgreSQL データ | TDE (Transparent Data Encryption) |
| Blob Storage | SSE (Storage Service Encryption) + CMK |
| Redis Cache | TLS 暗号化接続 |
| Key Vault シークレット | HSM バックド暗号化 |

### 3.2 個人情報取り扱い

- 従業員の氏名・メールアドレス・勤怠情報は個人情報に該当
- アクセスログを 1 年間保存
- 退職者データは退職後 5 年で自動削除

---

## 4. 脆弱性管理

### 4.1 依存ライブラリスキャン

- CI パイプラインで `pip-audit` / `safety` を実行
- Critical / High 脆弱性が検出された場合はデプロイをブロック
- 参考: INC0001017 で Spring Framework のパストラバーサル脆弱性 (CVE-2024-38816) が検出された事例あり。CI での自動検出を推奨。

### 4.2 定期脆弱性スキャン

| スキャン種別 | ツール | 頻度 |
|-------------|--------|------|
| 依存ライブラリ | pip-audit | 毎ビルド |
| コンテナイメージ | Trivy | 毎ビルド |
| インフラ構成 | Microsoft Defender for Cloud | 常時 |
| Web アプリ | OWASP ZAP | 月次 |

### 4.3 WAF ルール

Azure API Management + Azure Front Door で以下のルールを適用:

- SQL インジェクション検出・ブロック
- XSS (クロスサイトスクリプティング) 検出・ブロック
- パストラバーサル検出・ブロック
- Bot 検出・レート制限（INC0001013 対応で追加）

---

## 5. 監査ログ

### 5.1 記録対象

| イベント | ログレベル |
|---------|-----------|
| ログイン成功・失敗 | INFO / WARN |
| 権限変更 | INFO |
| 経費レポート承認・却下 | INFO |
| データエクスポート | INFO |
| 管理者操作 | INFO |
| 認証エラー（連続失敗） | ERROR |

### 5.2 ログ保存

| 保存先 | 保持期間 |
|--------|---------|
| Application Insights | 90 日 |
| Log Analytics Workspace | 1 年 |
| Storage Account (長期保存) | 7 年 |

---

## 6. インシデント対応

### 6.1 セキュリティインシデント分類

| レベル | 定義 | 対応時間 |
|--------|------|---------|
| Critical | データ漏洩、不正アクセス確認 | 即時 |
| High | 脆弱性悪用の試行検知 | 2 時間以内 |
| Medium | ポリシー違反の検知 | 24 時間以内 |
| Low | 情報収集行為の検知 | 翌営業日 |

### 6.2 対応フロー

```
検知 → トリアージ → 封じ込め → 根本原因分析 → 復旧 → ポストモーテム
```

- セキュリティインシデントは ServiceNow に自動起票
- Critical / High は Slack + 電話で即時エスカレーション
