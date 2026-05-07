# Security

## Sicherheitsannahmen

- Backend-Runtime: Python 3.11 slim, FastAPI, Uvicorn
- Frontend-Runtime: Nginx
- Persistenz: SQLAlchemy ueber `DATABASE_URL`, lokal mit SQLite-Fallback, produktiv PostgreSQL-ready
- Authentifizierung: JWT Bearer plus optionales TOTP-MFA
- Autorisierung: User/Admin-Rollen im Backend

## Positiv

- Backend-Container laeuft als `appuser`
- MFA ist implementiert
- Refresh-Token und Access-Token sind getrennt
- Passwort-Reset blendet User-Existenz nach aussen aus
- Passwort-Reset-Tokens werden nur gehasht gespeichert
- Passwort-Reset kann per SMTP an einen Frontend-Reset-Link zugestellt werden
- CORS ist auf explizite Origins begrenzt
- Alpaca-Secrets werden serverseitig verschluesselt gespeichert
- Login und Passwort-Reset sind rate-limitiert
- HTTP-Requests erzeugen jetzt korrelierbare strukturierte Logs mit `X-Request-ID`
- Audit-Logs vermeiden direkte E-Mail- und Push-Endpoint-Ausgabe
- Healthcheck ist vorhanden

## Kritische Risiken

- Frontend-Quellcode fehlt weiterhin; dadurch bleiben Security-Review, Supply-Chain-Pruefung und gezielte Haertung eingeschraenkt
- Produktive Push-Zustellung haengt jetzt explizit an gesetzten VAPID-Werten; fuer produktive Deployments muss `REQUIRE_VAPID_SECRETS=true` gesetzt und `tests/run-push-config-smoke.sh` gegen die Zielkonfiguration ausgefuehrt werden

## Mittlere Risiken

- SQLite ist fuer parallelen produktiven Mehrnutzerbetrieb und robuste Migrationen schwach
- Scanner und Streaming laufen unkoordiniert als Startup-Tasks ohne Lifecycle-Guardrails
- Watchlist-Alert-Dispatcher laeuft als Background-Task und braucht mittelfristig dieselben Telemetrie-, Locking- und Lifecycle-Guardrails wie andere Scheduler
- ML-Training pro Request ist teuer und potentiell missbrauchbar
- breit gefangene Exceptions erschweren an einzelnen Stellen weiterhin die Ursachenanalyse
- Hintergrundjobs und WebSockets tragen noch keine gleich starke Request-/Correlation-Telemetrie wie der HTTP-Pfad

## Hardening-Ziele

- Frontend-Quellstand beschaffen oder kontrolliert rekonstruieren
- Watchlists, Nutzereinstellungen und Transaktionen voll migrationsfaehig weiterentwickeln
- Background-Jobs und WebSockets auf dieselbe Telemetrie-/Audit-Qualitaet wie HTTP heben
- DB-Migrationen mit Alembic oder aehnlichem einfuehren

## Sofortmassnahmen

- produktive `VAPID_*`-Werte pro Zielumgebung setzen und mit `REQUIRE_VAPID_SECRETS=true` erzwingen
- Push-Konfigurations-Smoke-Test vor produktiven Rollouts laufen lassen; fuer Parser-only-Proben `GENERATE_TEST_VAPID=1 bash tests/run-push-config-smoke.sh` verwenden
- Frontend-Headerhaertung inkl. CSP und sichere Origin-Trennung definieren
- Secrets aus Exceptions und Betriebslogs weiter strikt fernhalten
- DB-Migrationspfad fuer PostgreSQL-first sauber nachziehen
