<!-- page: /news -->
# News-Hub

Ein einziger chronologischer Feed ueber alle News-Provider, an die die Plattform angeschlossen ist. Es geht nicht nur darum zu folgen, was mit deinen bestehenden Watchlist-Symbolen passiert — es geht darum, **neue Ticker zu entdecken**, die einen genaueren Blick verdienen.

## Quellen

- **FMP `/stock_news`** — globale Marktnews ohne Ticker-Filter, aus einer breiten Menge US-Finanz-Publisher.
- **Alpha Vantage `NEWS_SENTIMENT`** — themengetriebener Feed (technology, finance, earnings, economy_macro, economy_monetary). Items tragen den Sentiment-Score des Providers.
- **RSS-Feeds** — boerse.de (DE), ariva.de (DE), Reuters Markets. Symbol-agnostisch, Sentiment lokal mit VADER bewertet. Die Feed-Liste ist ueber die Env-Variable `RSS_NEWS_FEEDS` konfigurierbar (semikolon-getrennte `label|url`-Paare).

Alle Items werden per URL dedupliziert, neueste zuerst sortiert und upstream 5 Minuten gecacht, damit ein Page-Reload kein Provider-Budget verbrennt.

## Filter

- **Source** — auf eine einzelne Provider-Familie einschraenken.
- **Sentiment** — bullish / bearish / neutral, ueber VADER fuer RSS-Feeds berechnet, fuer FMP und Alpha Vantage uebernommen, falls vorhanden.
- **Time window** — letzte 1h / 6h / 24h / 3d / 7d, als `since`-Filter auf die API angewandt.
- **Symbol contains** — Exakt-Match gegen extrahierte Ticker pro Item. Probiere Namen aus, die du noch nicht trackst, um zu entdecken, was sich bewegt.

## Symbol-Chips

Jedes Item zeigt die enthaltenen Ticker als klickbare Chips, die direkt zur Analyse-Seite des Symbols springen. Ticker kommen aus:

- der eigenen Annotation des Providers (FMP liefert das Symbol am News-Objekt; Alpha Vantage liefert ein `ticker_sentiment`-Array)
- einem Regex ueber `$AAPL`-artige Erwaehnungen im Titel, wenn keine Annotation vorhanden ist (RSS-Feeds)

Wenn ein Symbol in deinen News auftaucht, das auf keiner deiner Watchlists ist, ist es ein Kandidat zum Hinzufuegen ueber die [Watchlists-Seite](/watchlists).

## Discovery-Hinweis

Der News-Hub ist die einfachste Discovery-Flaeche — "worueber redet der Markt gerade". Eine spaetere Welle ergaenzt eine dedizierte Stock-Discovery-Sicht (trending Symbole nach News-Volumen, Top-Gainer, Unusual Volume, Insider-Cluster) auf denselben Daten.
