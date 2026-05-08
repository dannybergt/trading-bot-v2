<!-- page: /news -->
# News hub

A single chronological feed across every news provider the platform is connected to. The point isn't just to follow what's happening with your existing watchlist symbols — it's to **discover new tickers** worth a closer look.

## Sources

- **FMP `/stock_news`** — global market news without a ticker filter, drawn from a wide set of US-finance publishers.
- **Alpha Vantage `NEWS_SENTIMENT`** — topic-driven feed (technology, finance, earnings, economy_macro, economy_monetary). Items carry the provider's own sentiment score.
- **RSS feeds** — boerse.de (DE), ariva.de (DE), Reuters Markets. Symbol-agnostic, sentiment scored locally with VADER. The feed list is configurable via the `RSS_NEWS_FEEDS` environment variable (semicolon-separated `label|url` pairs).

All items are deduplicated by URL, sorted newest-first, and cached for 5 minutes upstream so refreshing the page doesn't burn provider budgets.

## Filters

- **Source** — restrict to a single provider family.
- **Sentiment** — bullish / bearish / neutral, computed via VADER for the RSS feeds, taken from the provider for FMP and Alpha Vantage when present.
- **Time window** — last 1h / 6h / 24h / 3d / 7d, applied as `since` filter on the API.
- **Symbol contains** — exact match against extracted tickers per item. Try names you don't already track to discover what's moving.

## Symbol chips

Each item shows the tickers it mentions as clickable chips that jump straight to the analysis page for that symbol. Tickers come from:

- the provider's own annotation (FMP returns the symbol on the news object; Alpha Vantage returns a `ticker_sentiment` array)
- a regex over `$AAPL`-style mentions in titles when no annotation is present (RSS feeds)

If a symbol appears in your news that isn't on any of your watchlists yet, it's a candidate to add via the [Watchlists](/watchlists) page.

## Discovery hint

The news hub is the simplest discovery surface — "what is the market talking about right now". A future wave will add a dedicated stock-discovery view (trending symbols by news volume, top gainers, unusual volume, insider clusters) on top of the same data.
