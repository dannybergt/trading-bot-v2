<!-- page: /discover -->
# Discover

Three orthogonal views on "what's interesting right now?", surfaced from data the platform already pulls. The point is to find tickers worth a closer look that you don't already track — every symbol on the page is a clickable link straight into its analysis page.

## Trending in the news

Symbols mentioned most often in the global news feed (the same one that powers `/news`) over the last 24 hours, ranked by mention count. Each row carries:

- **Mentions 24h** — raw count over the window.
- **Trend %** — projected against the previous 6-day baseline. +500% means the symbol is being talked about six times more than its weekly average.
- **Sentiment** — average VADER score across the recent news items.
- **Burst** — delta between recent and baseline sentiment. A positive burst means the chatter is shifting bullish; negative means bearish.

A clear "high mention count + positive burst" combination is a watchlist candidate. The same combo with a negative burst is worth watching as a short candidate or a known-issue stock to avoid.

## Top movers

Today's biggest gainers, losers, and most-active US tickers (FMP `/stock_market/{gainers|losers|actives}`). The most-active column doubles as a poor-man's unusual-volume detector: a symbol the user doesn't track but the market is pumping volume into is exactly the kind of thing the discovery view exists for.

Each cell is a clickable link to the analysis page for that ticker.

## Insider clusters

Symbols where 3+ unique insiders filed transactions in the last 90 days. We pull the global insider feed (FMP v4 `/insider-trading-rss-feed`) and aggregate locally:

- **Insiders** — number of distinct people who filed.
- **Buy / Sell** — counts in each direction.
- **Net value** — buy-side dollars minus sell-side dollars.
- **Direction** — *buy_cluster* when more buys than sells, *sell_cluster* when reversed, *mixed* otherwise.

A "buy cluster" with a large positive net value where multiple officers all buy the same stock around the same time is one of the strongest non-public signals you can read.

## How fresh

The dashboard is cached for 15 minutes server-side. The query refetches automatically every 15 minutes too — manually reloading the tab earlier just hits the cache.

## Where the rules live

- Aggregation: `src/backend/app/discovery_service.py` (trending math, mover normalisation, cluster detection)
- Endpoint: `GET /api/discover`
- Helpers in `fmp_service`: `get_market_movers()`, `get_insider_trading_feed()`
