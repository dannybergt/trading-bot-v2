<!-- page: /admin -->
# Administration

Admin-only surface. Visible to users with the `is_admin` flag.

## Sections

- **Users** — list every account with role, status, and MFA flag. Actions: create new user, set password (recovery), reset MFA (when a user lost their authenticator), toggle active flag (ban/unban). Self-deactivation is blocked.
- **Backups** — every snapshot the scheduled backup task or the manual "Create snapshot" button has produced. Download as JSON or restore into the running database.
- **Platform export** — single-shot full database snapshot (every table, including `audit_events`). Used for migrations and disaster recovery.
- **Audit events** — paginated browser of the persistent audit trail. Filterable by user, by action. Identifying values (email, IP, user-agent) are stored as 16-character SHA-256 fingerprints, never plaintext.

## Audit-action vocabulary

The `action` column follows `<resource>.<verb>`. Notable entries:

- `auth.login` / `auth.login_failed` — login attempts (failure rows include the reason: invalid_credentials / account_inactive / invalid_mfa)
- `auth.register`, `auth.password_reset_confirm`, `auth.mfa_enable`, `auth.mfa_disable`, `auth.mfa_reset`
- `settings.alpaca_update`, `settings.portfolio_update`
- `paper_order.place`, `paper_order.place_rejected`, `paper_order.cancel`
- `backup.create`, `backup.restore`, `backup.export`, `backup.import`
- `admin.user_create`, `admin.user_password_reset`, `admin.user_toggle_active`

## How the audit log persists

The audit trail lives in the same database as everything else and is covered by every snapshot. A failed audit write logs and continues — the audit trail must never block the request path it is annotating.
