# ROADMAP — trading-bot-v2

> Skelett aus agent-baseline (AGENTS.md §16). `/status` baut aus diesen Phasen die Zweige seiner
> Plan-Karte; erledigte Punkte durchstreichen, nicht löschen.

## MVP

- [ ] _kleinster vertikaler Slice_

## Phase 2

- [ ] _…_

## Roadmap

- [ ] _…_

## Ideen (§12: MUST / SHOULD / COULD / ROADMAP — je Nutzen, Aufwand, Risiko)

| Idee | Klasse | Nutzen | Aufwand | Risiko |
|---|---|---|---|---|
| `alpaca-trade-api` -> `alpaca-py` (Thread 10) | SHOULD | beendet den `--no-deps`-Deckel aus ADR 2026-10-06, SDK wird gepflegt | mittel (REST + Stream, Antwortformen `/api/alpaca/*`) | Orderpfad; braucht Alpaca-Paper-Konto zum Nachweis |
| tailwindcss 3 -> 4 (Entscheidung bis 2026-10-20, Thread 21: dann laeuft die braces-Ausnahme ab und der CI-Audit wird rot) | SHOULD | beendet die braces-Ausnahme (GHSA-vfj7-8cjw-p6xm) und den postcss-selector-parser-Override | mittel (Config-Migration, UI optisch pruefen) | Darstellung; verifier mit Optik |
