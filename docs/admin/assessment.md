# Assessment

## Architektur

- Frontend: statisches Nginx-Bundle, Produktname `NexusPulse Trade`
- Backend: FastAPI-Monolith mit Marktanalyse, Auth, MFA, Push, Scanner und Alpaca-Anbindung
- Persistenz: SQLite plus dateibasierte Watchlists
- Integrationen: Alpaca, yfinance, Alpha Vantage, FIGI-Resolver, Browser Push
- ML: lokale Indikatoren plus `scikit-learn`/`xgboost`-gestuetzte Prognose

## Fachliche Staerken

- brauchbare Produktbreite fuer ein MVP bis Early-Stage-Produkt
- bereits vorhandene Auth-, MFA- und Admin-Flows
- integrierter Scanner und Push-Benachrichtigungen
- userbezogene Alpaca-Anbindung statt nur globaler Broker-Konfiguration

## Technische Schwaechen

- Backend ist ein stark gekoppelter Monolith
- globale In-Memory- und JSON-Watchlists statt sauberer User-Persistenz
- gemischte Verantwortlichkeiten in `app/main.py`
- sehr breite Fehlerbehandlung mit `print` statt strukturierter Telemetrie
- Frontend ohne Quellcode nur eingeschraenkt weiterentwickelbar

## Kritische Findings

- unsicherer JWT-Secret-Fallback in `src/backend/app/auth.py`
- offenes CORS in `src/backend/app/main.py`
- Alpaca-Secrets werden im Klartext gespeichert
- Watchlists sind nicht sauber pro User getrennt

## Update 2026-03-18

- JWT/CORS/Reset/Secret-Haertung ist umgesetzt
- Passwort-Reset-Delivery ueber SMTP und Frontend-Link ist umgesetzt
- Watchlists sind jetzt pro User in der Datenbank modelliert
- offene Restluecke: automatische Migration vorhandener `watchlists.json`-Bestände in die neuen Tabellen fehlt noch

## Pruefplan

1. Sicherheitsreview der Auth-, Reset-, Secret- und CORS-Pfade
2. API-Vertrag und Frontend-Abhaengigkeiten gegen reale Requests pruefen
3. Scanner-, Push- und Alpaca-Workflows mit kontrollierten Testdaten verifizieren
4. Persistenz- und Migrationspfad fuer Mehrnutzerbetrieb neu entwerfen
5. Frontend-Quellstand beschaffen oder rekonstruieren

## Entwicklungsplan

### Phase 1: Sicherheitsbaseline

- JWT-Secret ohne Fallback erzwingen
- CORS einschränken
- Rate-Limits fuer Login und Reset einfuehren
- Secrets serverseitig verschluesseln

### Phase 2: Daten- und Domänenmodell

- Watchlists, Push-Subscriptions und Nutzereinstellungen sauber normalisieren
- SQLite-Migrationspfad einziehen
- klare Modelle fuer Scanner-Ergebnisse und Alerts definieren

### Phase 3: Code-Struktur

- `main.py` in Router, Services und Domainmodule aufteilen
- Integrationen kapseln und mockbar machen
- Logging, Config und Fehlerbehandlung vereinheitlichen

### Phase 4: Frontend und Produkt

- Originalen Frontend-Quellstand beschaffen
- API-Client und UI-Zustände konsolidieren
- Signalqualitaet, Erklaerbarkeit und Fehlermeldungen verbessern

### Phase 5: Betrieb

- CI fuer Tests, Lint, Security-Checks und Image-Build
- reproduzierbare Releases
- Namensstrategie fuer Docker Hub und lokale Projektstruktur vereinheitlichen
