<!-- page: /paper-trading -->
# Paper trading

Place simulated orders against your watchlist universe. Fills run against the latest close with asset-class-specific slippage, and a Net-Yield-Gate refuses orders that would not clear your minimum yield once fees and capital-gains tax are accounted for.

## Tabs

- **Open orders** — pending limit orders waiting for the market to cross the limit. The background fill task re-evaluates them every three minutes.
- **Trade journal** — chronological list of every fill with quantity, price, fees, capital-gains tax, and both nominal and percent realized P&L. A time-range selector at the top of the tab (7 days / 30 days / 90 days / 1 year / All) filters the table client-side; the totals row recalculates against the filtered subset so realized P/L, fees, and tax always match what's on screen.
- **Positions** — current open positions with average entry price, last price, unrealized P&L, plus per-position fee and tax totals.
- **Summary** — totals across all transactions: realized P&L, unrealized P&L, fee total, tax total, open exposure, transaction count.

## How fills work

- **Market orders** — fill immediately at the latest close, with adverse slippage applied (stock 0.1%, ETF 0.05%, crypto 0.3%, scaled up by position size relative to the 20-day average volume, capped at 1%).
- **Limit orders** — fill when the latest close crosses the limit. They stay in "open" until they fill or you cancel them.

## How fees and tax work

Your broker fees come from the Settings → Portfolio defaults page. The simulator applies an asset-class fee multiplier on top: stock and ETF use 1×, crypto uses 5×, reflecting the typical Coinbase / Binance fee scale. Capital-gains tax is applied to realized profit only.

## Net-Yield-Gate

When you (or the recommendation card) supply a target price, the gate computes the net target percent after fees and tax. Orders below your `min_target_yield` are refused with a breakdown of gross / fees / tax / net so you can decide if you want to override manually.

## Auto vs manual orders

- **manual** — you fill in the form yourself. The gate only fires if you provided a target price.
- **auto-recommendation** — the order was created from the analysis page's "Place paper order at this target" link. Source carries through into the audit log.
