<!-- page: /auto-execution -->
# Auto-execution (Phase 4)

Phase 4 of the platform. Lets the system propose, evaluate, and (in future increments) place real broker orders against your Alpaca account — but only after every safety gate clears.

## How it ships

The master switch is **disabled by default**. No automation will run until you explicitly turn it on. Even with the switch on, no proposal becomes an order until it passes every gate listed below.

### Two modes

The page has a **Mode** selector with two values:

- **Paper (safe)** — default. Accepted proposals are routed into the internal paper-trading book. There is NO Alpaca call. Use this to validate the loop end-to-end with zero real-money exposure.
- **Live (Alpaca)** — accepted proposals go to your configured Alpaca account. **Important caveat: Alpaca is NOT a production broker for the operator of this instance** — Alpaca was wired up for paper-trading and live-quote streaming. The actual production broker (a separate adapter for the operator's real-money broker) is a follow-up phase. Until that adapter ships, treat Live-mode as "Alpaca-account routing only" — useful for testing the live-broker code path against a real broker API, NOT for routing your actual real-money trades. Switching into live mode requires an explicit confirmation step and is audited as a separate `auto_execution.live_mode_enabled` event.

The recommended path is: turn the master switch on → leave the mode on Paper → watch a few loop cycles → review the events log → only then consider Live.

## Paper auto-loop

A background task runs every 15 minutes (configurable via `AUTO_EXECUTION_PAPER_LOOP_INTERVAL_SECONDS`). For each user with `enabled=true AND mode=paper`:

1. The loop walks the union of watchlist symbols.
2. Each symbol is run through the existing prediction pipeline (`get_stock_data`).
3. Predictions with `direction=UP|DOWN` and `confidence >= 0.6` become proposals — qty = floor(`maxPositionSizeUsd` / entry).
4. Each proposal goes through `evaluate_proposal` (every risk gate + halt trigger + Net-Yield-Gate).
5. Allowed proposals are placed via `paper_trading.place_order` — same code path that powers manual paper trading.
6. Per-loop hard cap of 3 orders per user (configurable via `AUTO_EXECUTION_PAPER_MAX_TRADES_PER_LOOP`).

## Risk gates (per proposal)

1. **Master switch** must be `enabled`.
2. **Asset class** has to be in your allowlist (stock / etf / crypto). Empty allowlist = nothing automated.
3. **Position size** (qty × limit price) has to fit under your `Max position size`.
4. **Daily loss budget** must still have room — today's realized P&L is summed against `Max daily loss`.
5. **Open positions** count has to be below `Max open positions`.
6. **Net-Yield-Gate** — same broker-fee + capital-gains-tax math the explainer and paper-trading already use. Net target % has to clear your `min_target_yield`.

## Halt triggers (external data)

These are evaluated using the macro and SEC-filings data the platform already fetches:

- **FOMC < 24h** — checked against the FRED upcoming-releases calendar (`category=policy`).
- **Recent 8-K material event** — symbol-specific. If FMP shows an 8-K within the last 7 days, automation halts for that symbol.
- **Yield curve inverted** — when FRED's 10Y-2Y spread (`T10Y2Y`) goes negative, automation halts on stocks/ETFs (crypto is exempt, since the curve doesn't drive its risk model).
- **Symbol beta > limit** — your `Max symbol beta vs SPY` from the limits form is checked against `sectorContext.correlation.beta`.

Each rejection appears in the events log with the exact reason code, so you can tell at a glance whether the halt was due to risk-budget, asset-class allowlist, or one of the macro halts.

## Stop button

The "Stop all automation" button immediately flips the master switch off and writes a `halted` audit row. Phase 4d reconciliation will additionally cancel any open Alpaca limit orders. Use this whenever you want a clean break.

## What is NOT yet wired

- No background loop is automatically calling `evaluate_proposal`. Phase 4 ships the safety infrastructure first; the actual auto-trade loop will be added in a follow-up commit and gated behind another explicit user opt-in.
- Phase 4d reconciliation will close the loop with Alpaca: open-position counts will use the broker's live state instead of the local paper-trading proxy, and the halt button will cancel real orders.

## Audit trail

Every evaluation (`accepted` / `rejected`), every halt (`halted`), and every limit change is written to `auto_execution_events`. The list at the bottom of the page reads from there, newest-first.
