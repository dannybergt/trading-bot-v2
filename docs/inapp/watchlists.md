<!-- page: /watchlists -->
# Watchlists

Watchlists are the named collections of symbols you actively follow. Every other surface (scanner, alerts, paper trading recommendations) is filtered by the active watchlist.

## What you see

- **One card per watchlist** with its symbols, names, and tags. The default seed watchlists ("Tech Giants", "Crypto Proxies") are created on first sign-in.
- **Add-item form** at the bottom of each card — symbol, optional human-friendly name, comma-separated tags.

## Symbols

- **Stocks** use plain tickers (AAPL, MSFT, NVDA).
- **ETFs** use plain tickers too (VOO, SPY, XLK).
- **Crypto** uses the slash-separated form (BTC/USD, ETH/USD).
- **Non-US equities** use the exchange suffix (SAP.DE, BMW.DE, LVMH.PA, 7203.T).

## Tags

Tags are free-text labels you attach to a watchlist item. Alert rules can match on tags ("everything tagged 'priority' should fire on negative news"), so they're a useful organizing layer once your watchlist grows.

## How it persists

Watchlist data is stored in the application database and covered by every backup, export, and import.
