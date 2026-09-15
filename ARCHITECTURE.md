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
