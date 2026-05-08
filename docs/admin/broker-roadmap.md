# Broker-Adapter Roadmap (Phase 4f)

Stand 2026-05-08. Verbindlich fuer den Live-Trade-Pfad. Live-Mode ist im Code hart gesperrt (`auto_execution.LIVE_MODE_LOCKED=True`) — diese Sperre wird erst gehoben wenn ein verifizierter Adapter pro Ziel-Broker geliefert ist.

## Architekturprinzip

Pro Broker eine eigene Datei unter `src/backend/app/brokers/<name>.py`, alle implementieren ein gemeinsames `BrokerAdapter`-Interface:

```
class BrokerAdapter(Protocol):
    name: str            # "trade-republic", "flatex", "bitvavo", ...
    def connect(creds: dict) -> ConnectionHandle
    def get_account() -> AccountSnapshot
    def get_positions() -> list[Position]
    def get_open_orders() -> list[Order]
    def place_limit_order(symbol, side, qty, limit_price, target_price=None) -> Order
    def cancel_order(order_id) -> bool
    def reconcile() -> ReconciliationReport
```

`auto_execution_paper_loop_task` bleibt unangetastet. Ein neuer `auto_execution_live_loop_task` wird in derselben Form aufgesetzt, ruft aber `BrokerAdapter.place_limit_order` statt `paper_trading.place_order`. Per-User-Setting `live_broker_adapter` (string) waehlt aus den verfuegbaren Adaptern.

## Auswahl-Liste

Geplante Adapter, sortiert nach API-Reife (am einfachsten zu integrieren = oben):

| Broker | Asset-Klassen | API-Status | Komplexitaet | Region |
|---|---|---|---|---|
| **Interactive Brokers** | Stocks/ETF/Optionen/Futures/FX | TWS-API + IBKR REST, offiziell | mittel-hoch | global |
| **Saxo Bank** | Stocks/ETF/Optionen/Bonds/FX | OpenAPI offiziell, OAuth2 | mittel | EU + global |
| **Bitvavo** | Krypto | REST + WebSocket offiziell, API-Key | niedrig | EU |
| **Coinbase Advanced** | Krypto | REST + WebSocket offiziell, OAuth2 | niedrig | global |
| **Kraken** | Krypto | REST + WebSocket offiziell, API-Key | niedrig | global |
| **Bitpanda** | Krypto + Edelmetalle | REST offiziell (Pro), API-Key | niedrig | EU |
| **Alpaca Live** | US-Stocks/ETF/Krypto | REST + WebSocket offiziell, API-Key (bereits integriert fuer Quotes/Paper) | niedrig | US |
| **Lemon Markets** | DE-Stocks/ETF | REST offiziell, API-Key, Paper+Live | niedrig | DE |
| **Trade Republic** | DE-Stocks/ETF/Krypto | KEIN offizielles API; Reverse-Engineered (`pytr`-aehnlich) | hoch + fragil | DE |
| **Scalable Capital (Trader-Pro)** | Stocks/ETF/Krypto | Inoffiziell ueber WebSocket; Public-API nur fuer institutional | hoch | DE |
| **Flatex** | Stocks/ETF/Optionen | KEIN oeffentliches API; Web-Login + ggf. FIX (institutional) | sehr hoch | DE/AT |
| **Comdirect** | Stocks/ETF/Optionen | KEIN oeffentliches API; Push-TAN-/Photo-TAN-Zwang | sehr hoch | DE |
| **DKB Broker** | Stocks/ETF | KEIN oeffentliches API | sehr hoch | DE |
| **Consorsbank** | Stocks/ETF | KEIN oeffentliches API | sehr hoch | DE |
| **Smartbroker+ / Justtrade** | DE-Stocks/ETF/Krypto | KEIN oeffentliches API | sehr hoch | DE |
| **Zero (z.B. Scalable Zero / Free-Tier)** | Stocks/ETF | je nach Anbieter; Scalable Zero nutzt Trader-Pro-Backend | hoch | DE |

Realistische Reihenfolge (am User auszurichten):

1. **Phase 4f-1** — *Krypto-Track*: **Bitvavo** ODER **Kraken** (offizielles API, klein, gut testbar). User-bevorzugtem Broker entsprechend.
2. **Phase 4f-2** — *Stocks/ETF-Track-EU*: **Lemon Markets** (DE-spezifisch, offizielles API, Paper+Live separierbar). Saubere Bruecke fuer DE-Werte.
3. **Phase 4f-3** — *Stocks/ETF-Track-Profi*: **Interactive Brokers** ODER **Saxo OpenAPI**. Volle Asset-Klassen-Abdeckung.
4. **Phase 4f-4** — *Wunsch-Broker des Operators (Trade Republic / Comdirect / Flatex / ...)*: nur wenn der Operator wirklich auf einem dieser Broker landet. Reverse-engineered Adapter werden separat security-reviewed; keine Garantie auf Stabilitaet ueber Broker-Updates hinaus.

## Sicherheits-Constraints

- API-Keys + OAuth-Tokens liegen in `.env.local` (Mode 600, gitignored), niemals im Code.
- Pro Broker eigene Audit-Action-Praefixe (`broker.bitvavo.order_placed`, `broker.kraken.cancel`, …).
- Reconciliation-Task ist Pflicht — ohne periodischen Sync zwischen lokaler DB und Broker-Status startet kein Live-Loop.
- Not-Aus muss broker-spezifisch alle offenen Orders cancelt vor er das `enabled=false` setzt.
- LIVE_MODE_LOCKED wird pro deploy einzeln umgelegt; never via Env-Variable, nur via Code-Aenderung mit Review.

## Offene User-Entscheidung

Der Operator nutzt aktuell weder Alpaca noch einen der oben gelisteten Broker als produktiven Real-Money-Broker. Vor jedem Adapter-Build steht die Frage: welcher Broker zuerst? Die Empfehlung priorisiert nach Track-1 (Krypto, niedrigschwellig) → Track-2 (DE-Stocks/ETF) → Track-3 (Profi). User-Antwort hat Vorrang.
