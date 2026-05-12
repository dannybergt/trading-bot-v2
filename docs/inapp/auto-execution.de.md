<!-- page: /auto-execution -->
# Auto-Execution (Phase 4)

Phase 4 der Plattform. Erlaubt dem System, Vorschlaege zu erzeugen, zu bewerten und (in spaeteren Inkrementen) echte Broker-Orders gegen dein Alpaca-Konto zu platzieren — aber nur, wenn jedes Sicherheits-Gate gruen ist.

## Auslieferungs-Modell

Der Master-Switch ist **per Default deaktiviert**. Solange er aus ist, laeuft keine Automatisierung. Auch mit aktivem Schalter wird kein Vorschlag zur Order, bevor er saemtliche unten gelisteten Gates passiert hat.

### Zwei Modi

Die Seite hat einen **Mode**-Selektor mit zwei Werten:

- **Paper (safe)** — Default. Angenommene Vorschlaege landen im internen Paper-Trading-Buch. Es gibt KEINEN Alpaca-Call. Damit kannst du den Loop end-to-end pruefen ohne Echtgeld-Exposure.
- **Live — aktuell im Code HART GESPERRT.** Der Radio-Button ist disabled und mit "Locked" gelabelt. Das Backend lehnt jeden Payload ab, der `mode=live` setzen wuerde. Die Sperre faellt erst, wenn Phase 4f einen verifizierten Broker-Adapter fuer den vom Operator gewaehlten Echtgeld-Broker (Trade Republic, Flatex, Comdirect, Bitvavo, Kraken, Interactive Brokers, …) liefert. Siehe `docs/admin/broker-roadmap.md` fuer den vollstaendigen Plan. Keine Env-Variable, kein Settings-Page, kein Admin-Button kann das umflippen — nur ein Code-Change plus Security-Review.

Empfohlener Pfad: Master-Switch an → Mode auf Paper lassen → ein paar Loop-Cycles beobachten → Events-Log pruefen → erst dann Live in Erwaegung ziehen.

## Paper-Auto-Loop

Ein Background-Task laeuft alle 15 Minuten (konfigurierbar via `AUTO_EXECUTION_PAPER_LOOP_INTERVAL_SECONDS`). Fuer jeden User mit `enabled=true AND mode=paper`:

1. Der Loop wandert die Vereinigung der Watchlist-Symbole ab.
2. Jedes Symbol laeuft durch die bestehende Prediction-Pipeline (`get_stock_data`).
3. Predictions mit `direction=UP|DOWN` und `confidence >= 0.6` werden zu Vorschlaegen — qty = floor(`maxPositionSizeUsd` / entry).
4. Jeder Vorschlag durchlaeuft `evaluate_proposal` (alle Risk-Gates + Halt-Trigger + Net-Yield-Gate).
5. Erlaubte Vorschlaege werden via `paper_trading.place_order` platziert — gleicher Code-Pfad wie das manuelle Paper-Trading.
6. Hard-Cap pro Loop: 3 Orders pro User (konfigurierbar via `AUTO_EXECUTION_PAPER_MAX_TRADES_PER_LOOP`).

## Risk-Gates (pro Vorschlag)

1. **Master-Switch** muss `enabled` sein.
2. **Asset-Klasse** muss in deiner Allowlist sein (stock / etf / crypto). Leere Allowlist = nichts wird automatisiert.
3. **Position-Size** (qty x limit price) muss unter dein `Max position size` passen.
4. **Daily-Loss-Budget** muss noch Platz haben — der heutige realisierte P&L wird gegen `Max daily loss` summiert.
5. **Open-Positions**-Anzahl muss unter `Max open positions` liegen.
6. **Net-Yield-Gate** — dieselbe Broker-Fee- + Kapitalertragssteuer-Rechnung, die der Explainer und das Paper-Trading bereits nutzen. Netto-Ziel-Prozent muss `min_target_yield` ueberschreiten.

## Halt-Trigger (externe Daten)

Diese werden gegen die Macro- und SEC-Filings-Daten gepruepft, die die Plattform sowieso holt:

- **FOMC < 24h** — gegen den FRED-Upcoming-Releases-Kalender geprueft (`category=policy`).
- **Recent 8-K material event** — symbolspezifisch. Wenn FMP ein 8-K innerhalb der letzten 7 Tage zeigt, wird die Automatisierung fuer dieses Symbol gestoppt.
- **Yield-Curve invertiert** — wenn FREDs 10Y-2Y-Spread (`T10Y2Y`) negativ ist, wird die Automatisierung auf Stocks/ETFs gestoppt (Crypto ist ausgenommen, weil die Kurve dort nicht risikobestimmend ist).
- **Symbol-Beta > Limit** — dein `Max symbol beta vs SPY` aus dem Limits-Formular wird gegen `sectorContext.correlation.beta` geprueft.

Jede Ablehnung erscheint im Events-Log mit konkretem Reason-Code, so dass auf einen Blick erkennbar ist, ob der Halt durch Risk-Budget, Asset-Class-Allowlist oder einen der Macro-Halts ausgeloest wurde.

## Stop-Button

Der Button "Stop all automation" flippt den Master-Switch sofort aus und schreibt eine `halted`-Audit-Zeile. Die Phase-4d-Reconciliation wird zusaetzlich offene Alpaca-Limit-Orders canceln. Nutzen, wann immer ein sauberer Schnitt gewollt ist.

## Was noch NICHT verdrahtet ist

- Kein Background-Loop ruft automatisch `evaluate_proposal` auf. Phase 4 liefert zuerst die Sicherheits-Infrastruktur; der eigentliche Auto-Trade-Loop kommt in einem Folge-Commit und ist hinter einem weiteren expliziten User-Opt-In abgesichert.
- Die Phase-4d-Reconciliation schliesst den Loop gegen Alpaca: Open-Position-Counts kommen dann aus dem Live-State des Brokers statt aus dem lokalen Paper-Trading-Proxy, und der Halt-Button cancelt echte Orders.

## Audit-Trail

Jede Bewertung (`accepted` / `rejected`), jeder Halt (`halted`) und jede Limit-Aenderung wird in `auto_execution_events` geschrieben. Die Liste am Seitenende liest daraus, neueste zuerst.
