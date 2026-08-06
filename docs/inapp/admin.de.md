<!-- page: /admin -->
# Administration

Admin-Bereich. Sichtbar fuer Konten mit dem `is_admin`-Flag.

## Sektionen

Die Seite gibt es auf Deutsch und Englisch; sie folgt dem Sprach-Umschalter im
Kopfbereich wie jede andere Seite auch.

- **Nutzer** — alle Konten mit Rolle, Status und MFA-Flag. Aktionen: neuen Nutzer anlegen, Passwort setzen (Recovery), MFA zuruecksetzen (wenn jemand seinen Authenticator verloren hat), Active-Flag umschalten (Bann/Entbann). Selbstdeaktivierung ist blockiert.
- **Datenquellen** — welche Anbieter die Empfehlungs-Engine speisen, ob sie konfiguriert sind und was die naechste kostenpflichtige Stufe brächte. Anbieter mit API-Schluessel sind hier direkt setzbar: der Wert liegt verschluesselt in der Datenbank (Fernet / `APP_ENCRYPTION_KEY`), die Lesereihenfolge ist Datenbank > Umgebungsvariable > nicht konfiguriert, und ein 60-Sekunden-Cache uebernimmt einen neuen Wert ohne Neustart. "Speichern & testen" fragt den echten Anbieter ab.
- **Gewichte der Gesamtentscheidung** — relatives Gewicht jeder Quelle (Technisch/ML, Analysten-Konsens, Fundamentaldaten, Nachrichten-Stimmung) im kombinierten KAUFEN/HALTEN/VERKAUFEN-Verdikt, auf 100 % normalisiert. Die Kalibrierung schreibt neue Gewichte nur, wenn sie die aktuelle Trefferquote auf den gesammelten Forward-Daten schlagen.
- **Sicherungen** — jeder Snapshot, den der geplante Backup-Task oder der Button "Sicherung manuell erstellen" erzeugt hat. Download als JSON.
- **Export** — einmaliger kompletter Datenbank-Snapshot (alle Tabellen, inklusive `audit_events`). Wird fuer Migrationen und Disaster Recovery genutzt.

Der unten beschriebene Audit-Trail wird vom Backend geschrieben und vom Export
mit abgedeckt, hat auf dieser Seite aber **keine** eigene Ansicht — er ist ueber
`GET /api/admin/audit-events` abrufbar.

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
