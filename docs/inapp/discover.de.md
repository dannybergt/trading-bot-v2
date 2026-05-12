<!-- page: /discover -->
# Discover

Drei orthogonale Sichten auf "was ist gerade interessant?", aus Daten gewonnen, die die Plattform ohnehin holt. Der Punkt ist, Ticker zu finden, die du noch nicht trackst — jedes Symbol auf der Seite ist ein klickbarer Link direkt zur Analyse-Seite.

## Trending in den News

Symbole, die im globalen News-Feed (derselbe Feed, der `/news` speist) in den letzten 24 Stunden am haeufigsten erwaehnt wurden, sortiert nach Mention-Count. Jede Zeile zeigt:

- **Mentions 24h** — Rohzaehlung im Fenster.
- **Trend Prozent** — projiziert gegen die 6-Tage-Baseline davor. +500 Prozent heisst, das Symbol wird sechsmal haeufiger besprochen als der Wochendurchschnitt.
- **Sentiment** — durchschnittlicher VADER-Score ueber die juengsten News.
- **Burst** — Delta zwischen juengstem und Baseline-Sentiment. Positiver Burst = das Geraeusch dreht bullish; negativer Burst = bearish.

Die Kombination "hoher Mention-Count + positiver Burst" ist ein Watchlist-Kandidat. Dieselbe Kombi mit negativem Burst lohnt sich als Short-Kandidat oder als Known-Issue-Stock zum Meiden.

## Top Movers

Die groessten Tagesgewinner, -verlierer und meistgehandelten US-Ticker (FMP `/stock_market/{gainers|losers|actives}`). Die Most-Active-Spalte funktioniert als grober Unusual-Volume-Detektor: ein Symbol, das du nicht trackst, in das der Markt aber Volumen pumpt, ist genau das, wofuer der Discover-Blick da ist.

Jede Zelle ist ein klickbarer Link zur Analyse-Seite des jeweiligen Tickers.

## Insider-Cluster

Symbole, in denen 3 oder mehr verschiedene Insider in den letzten 90 Tagen Transaktionen gemeldet haben. Der globale Insider-Feed (FMP v4 `/insider-trading-rss-feed`) wird gezogen und lokal aggregiert:

- **Insiders** — Anzahl unterschiedlicher Personen mit Filings.
- **Buy / Sell** — Counts pro Richtung.
- **Net value** — Buy-Side-USD minus Sell-Side-USD.
- **Direction** — *buy_cluster* wenn mehr Buys als Sells, *sell_cluster* wenn umgekehrt, sonst *mixed*.

Ein "Buy Cluster" mit grossem positivem Netto-Wert, in dem mehrere Officer um denselben Zeitpunkt kaufen, ist eines der staerksten nicht-oeffentlichen Signale, die du lesen kannst.

## Wie aktuell

Das Dashboard wird serverseitig 15 Minuten gecacht. Der Query refetched ebenfalls alle 15 Minuten — manuelles Tab-Reloaden trifft frueher nur den Cache.

## Wo die Regeln liegen

- Aggregation: `src/backend/app/discovery_service.py` (Trending-Mathematik, Mover-Normalisierung, Cluster-Detection)
- Endpoint: `GET /api/discover`
- Helpers in `fmp_service`: `get_market_movers()`, `get_insider_trading_feed()`
