<!-- page: / -->
# Dashboard

The dashboard is the single landing surface for everything you watch and everything that needs your attention right now.

## What you see

- **Setup progress card** — top of the page, only shown until every onboarding step is configured. It links into the wizard for whatever you still owe (broker keys, fees, tax rate, MFA).
- **Active watchlist selector** — every other section follows this choice.
- **Tracked assets** — every symbol from the active watchlist with its asset class (Stock / ETF / Crypto), tags, and a link straight into the analysis page.
- **Provider coverage** — small KPI cards counting how many of your tracked symbols have live provider data, partial coverage, or no data at all. Useful when something looks "empty": it tells you whether the provider is silent or you simply don't track anything in that asset class.
- **Watchlist alerts** — priority-ranked list of trade-relevant items pulled from your alert configuration.
- **News ticker** — rolling headlines for the active watchlist; each item links to the source.

## How it updates

The watchlist alerts auto-refresh roughly every minute. News, tracked assets, and provider coverage are cached separately so the slower alert path can't block them — you'll see them populate in stages on cold loads.

## Common actions

- **Create or rename a watchlist** → the [Watchlists page](/watchlists).
- **Investigate a single symbol** → click the symbol in any tracked-assets card.
- **Configure alerts** → [Alerts](/alerts) for rule CRUD.
