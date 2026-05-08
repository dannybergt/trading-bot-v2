<!-- page: /analysis -->
# Symbol analysis

The deepest single-symbol surface. Pulls every signal we have for the symbol and renders them stacked from "what does the model think" down to "raw news headlines".

## What you see

- **ML signal card** — direction (UP / DOWN / HOLD), confidence, P(UP)/P(DOWN) bars, top features and category breakdown (Trend / Technical / Volume / News / Fundamentals), entry / stop / target zones, and a yield breakdown that subtracts your broker fees and capital-gains tax. The "Place paper order at this target" link prefills the paper-trading form.
- **Chart** — candles plus toggleable overlays (SMA, EMA, VWAP, Bollinger Bands), sub-panes for RSI and MACD, pattern arrows (engulfing, hammer, doji…), auto-detected support and resistance lines, and your paper-trade markers if you've placed any.
- **Volume profile** — horizontal histogram next to the chart with the point-of-control highlighted.
- **Fundamentals** — sector, industry, market cap, P/E, P/B, 52-week range. Sourced from yfinance with FMP and Twelve Data as fallbacks.
- **Model performance** — walk-forward backtest of the persisted predictor. Shows direction accuracy, AUC, Brier score, the cumulative return of a long-when-UP strategy vs buy-and-hold, plus a calibration table that tells you whether the P(UP) numbers are honest.
- **Research depth** (FMP) — recent cash-flow, debt highlights, analyst rating, forward EPS / revenue estimates.
- **Research signals** — insider transactions (last 90 days), top institutional holders, earnings beat history, next earnings date.
- **Earnings call digest** — VADER-scored summary of the most recent transcripts with the highest-positive and highest-negative sentence as quotes.
- **Crypto metrics** (only for crypto symbols) — market cap rank, 24h cross-exchange volume, ATH/ATL distance, developer and community activity from CoinGecko.
- **Retail sentiment** — combined StockTwits and Reddit chatter from the last 24 hours, with a sentiment score weighted by message volume.
- **Options flow** (US-listed equities) — put/call ratios for volume and open interest, ATM implied volatility, top three strikes per side. A skew label classifies the chain bullish / bearish / neutral.
- **Macro context** — VIX, 10-year Treasury yield, U.S. Dollar Index, and the Crypto Fear-and-Greed Index. The "weather report" you should read every per-symbol signal in.
- **Sector relative strength** — trailing return spread vs SPY, QQQ, IWM, and the matching sector ETF (XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLB, XLU, XLRE, XLC). Plus 90-day correlation and beta to SPY. Positive alpha means the symbol is leading its peers; high beta means it amplifies SPY moves.
- **SEC filings** — EDGAR filings index via FMP, classified into annual (10-K), quarterly (10-Q), material events (8-K), proxy statements (DEF 14A), offerings, and insider forms. Each entry links straight to the SEC document. The "last 8-K" timestamp is a rough freshness gauge for material news that hasn't necessarily reached the news feed yet.
- **Events** — earnings dates, dividends, splits.
- **Holdings** — for ETFs, top holdings with weight.
- **News** — aggregated news with VADER sentiment per item.

## How recommendations are gated

A buy-side recommendation is only "actionable" when the projected NET return after broker fees and capital-gains tax clears your `min_target_yield`. The yield breakdown card spells out gross / fees / tax / net.
