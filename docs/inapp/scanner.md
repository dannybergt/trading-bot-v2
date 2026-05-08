<!-- page: /scanner -->
# Scanner

The scanner pulls today's market move for every symbol on the active watchlist and ranks them by absolute change. It's a quick way to see "what's moving in my universe right now".

## What you see

- **Sortable list** of your watchlist symbols with current price, day change %, and an asset-class label.
- **Provider-status pills** — green when the provider returned a live quote, yellow for partial coverage, gray when no provider answered.
- **Asset-mix breakdown** at the top — how many stocks, ETFs, and crypto symbols you're tracking.

## Why values can be missing

- yfinance occasionally throttles; the cell will show "—" until the next refresh succeeds.
- Crypto symbols use the Alpha Vantage path; if `ALPHA_VANTAGE_API_KEY` is not configured the cell is empty.
- Non-US symbols fall through to Twelve Data; if that's also unconfigured the row stays empty until at least one provider answers.

## Common actions

- **Open analysis** for a symbol by clicking the row. Takes you to the full single-symbol view.
- **Add a new symbol** — go back to [Watchlists](/watchlists). The scanner immediately picks it up on next refresh.
