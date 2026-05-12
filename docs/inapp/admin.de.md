<!-- page: /admin -->
# Administration

Admin-Bereich. Sichtbar fuer Konten mit dem `is_admin`-Flag.

## Sektionen

- **Users** — alle Konten mit Rolle, Status und MFA-Flag. Aktionen: neuen Nutzer anlegen, Passwort setzen (Recovery), MFA zuruecksetzen (wenn jemand seinen Authenticator verloren hat), Active-Flag umschalten (Bann/Entbann). Selbstdeaktivierung ist blockiert.
- **Backups** — jeder Snapshot, den der geplante Backup-Task oder der manuelle Button "Create snapshot" erzeugt hat. Download als JSON oder Restore in die laufende Datenbank.
- **Platform export** — einmaliger kompletter Datenbank-Snapshot (alle Tabellen, inklusive `audit_events`). Wird fuer Migrationen und Disaster Recovery genutzt.
- **Audit events** — paginierter Browser des persistenten Audit-Trails. Filter nach Nutzer, nach Action. Identifizierende Werte (E-Mail, IP, User-Agent) werden als 16-Zeichen-SHA-256-Fingerprints gespeichert, nie im Klartext.

## Audit-Action-Vokabular

Die `action`-Spalte folgt dem Schema `<resource>.<verb>`. Wichtige Eintraege:

- `auth.login` / `auth.login_failed` — Login-Versuche (Failure-Zeilen enthalten den Grund: invalid_credentials / account_inactive / invalid_mfa)
- `auth.register`, `auth.password_reset_confirm`, `auth.mfa_enable`, `auth.mfa_disable`, `auth.mfa_reset`
- `settings.alpaca_update`, `settings.portfolio_update`
- `paper_order.place`, `paper_order.place_rejected`, `paper_order.cancel`
- `backup.create`, `backup.restore`, `backup.export`, `backup.import`
- `admin.user_create`, `admin.user_password_reset`, `admin.user_toggle_active`

## Wie der Audit-Log persistiert

Der Audit-Trail liegt in derselben Datenbank wie alles andere und wird von jedem Snapshot mit abgedeckt. Ein fehlgeschlagener Audit-Write loggt und macht weiter — der Audit-Trail darf den annotierten Request-Pfad nie blockieren.
