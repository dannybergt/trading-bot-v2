# ARCHITECTURE — trading-bot-v2

> Skelett aus agent-baseline (AGENTS.md §0). Füllen, sobald die erste Komponente steht; jede
> nicht-triviale Entscheidung dazu als ADR in `DECISIONS.md`.

## Komponenten

| Komponente | Verantwortung | Technologie | Läuft als |
|---|---|---|---|
| _api_ | _…_ | _…_ | _Container `trading-bot-v2-api`_ |

## Datenflüsse

_Wer ruft wen, mit welchen Daten, über welche Grenze (HTTP, Queue, DB). Ein Diagramm (ASCII oder
Mermaid) reicht._

## Grenzen und Vertrauen

- Externe Eingaben (Nutzer, Webhooks, Dateien): _wo validiert?_ (§2.5, §6)
- Mandanten-/Datenisolation: _falls relevant_
- Secrets: _nur über ENV/Secret-Manager; Liste in `.env.example`_

## Tech-Stack

_Sprachen, Frameworks, Datenbank, Build, Deploy (Compose auf welcher Node?)._

## Bekannte Grenzen („Deckel")

_Bewusste Vereinfachungen mit der Bedingung, die ihre Ablösung rechtfertigt (§2.5)._

| Deckel | Wert | Wo | Abloese-Ausloeser |
|---|---|---|---|
| Backtest-Jobs je Prozess | 8 (`BACKTEST_MAX_JOBS`) | `backtest_service.py` | `backtest_queue_full` im Log |
| Backtest-Anteil je Nutzer | 3 offene Jobs, 12 Enqueues / 10 min (`BACKTEST_MAX_JOBS_PER_USER`, `BACKTEST_ENQUEUES_PER_USER`) | `backtest_service.py` | `backtest_user_quota_full` im Log bei einem echten Nutzer |
| Watchlist-Zeilen je Konto | 200 ueber alle Listen (`WATCHLIST_MAX_ITEMS_PER_USER`) | `main.py`, nur Member-Tueren (`add_item`); Admin-Import und Registrierungs-Seed nicht gedeckelt | `watchlist_user_quota_full` im Log bei einem Nutzer mit echtem Portfolio (ADR 2026-09-20) |
| Watchlisten je Konto | 50 (`WATCHLIST_MAX_LISTS_PER_USER`) | `main.py` (`create_watchlist`) | dito |
| Zaehlen und Anlegen nicht atomar | Ueberschuss ≈ gleichzeitige Anfragen eines Kontos, einmalig | `require_watchlist_quota` | Ueberschuss taucht in der Zaehlung auf → `SELECT … FOR UPDATE` |
| Name einer Liste/Zeile | 200 Zeichen (`WATCHLIST_NAME_MAX`), Symbol 64 | `main.py`, alle vier Schreibpfade | — |
