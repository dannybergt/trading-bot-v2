<!-- page: /analysis -->
# Symbol-Analyse

Die tiefste Single-Symbol-Flaeche. Holt jedes Signal, das wir zum Symbol haben, und stapelt sie von "was denkt das Modell" bis "rohe News-Schlagzeilen".

## Was du siehst

- **ML-Signal-Karte** — Richtung (UP / DOWN / HOLD), Confidence, P(UP)/P(DOWN)-Balken, Top-Features und Kategorie-Aufschluesselung (Trend / Technical / Volume / News / Fundamentals), Entry-/Stop-/Target-Zonen und eine Yield-Aufschluesselung, die Broker-Gebuehren und Kapitalertragssteuer abzieht. Der Link "Place paper order at this target" befuellt das Paper-Trading-Formular vor.
- **Chart** — Candles plus umschaltbare Overlays (SMA, EMA, VWAP, Bollinger Bands), Sub-Panes fuer RSI und MACD, Pattern-Pfeile (engulfing, hammer, doji…), automatisch erkannte Support-/Resistance-Linien sowie deine Paper-Trade-Marker, falls vorhanden.
- **Volume Profile** — horizontales Histogramm neben dem Chart mit hervorgehobenem Point-of-Control.
- **Fundamentals** — Sektor, Branche, Marktkapitalisierung, KGV, KBV, 52-Wochen-Range. Quelle yfinance, mit FMP und Twelve Data als Fallbacks.
- **Fundamentals-Detail** (FMP) — expliziter Kennungs- und Fundamentals-Block in vier Sub-Sektionen: *Kennungen* (ISIN, WKN aus DE-ISINs abgeleitet, CUSIP, Boerse, Waehrung), *Bewertung* (Marktkap, KGV TTM, Forward-KGV, KBV TTM, KUV TTM, Beta), *Gewinn & Bilanz* (EPS TTM, juengster Jahres-Umsatz und Gewinn mit Fiscal-Year-Datum, Eigenkapitalrendite TTM, Verschuldungsgrad TTM), *Dividende* (Rendite TTM, Summe der Dividenden der letzten 365 Tage, Ausschuettungsquote TTM). Die WKN wird mechanisch aus DE-ISINs abgeleitet (Positionen 6-11) und erscheint nur fuer deutsche Notierungen; Nicht-DE-Symbole lassen das Feld weg.
- **Model performance** — Walk-Forward-Backtest des persistierten Predictors. Zeigt Direction-Accuracy, AUC, Brier-Score, den kumulierten Return einer Long-when-UP-Strategie vs Buy-and-Hold sowie eine Kalibrierungs-Tabelle, die anzeigt, ob die P(UP)-Werte ehrlich sind.
- **Research depth** (FMP) — aktuelle Cash-Flow-Daten, Debt-Highlights, Analyst-Rating, Forward-EPS-/Umsatz-Schaetzungen.
- **Research signals** — Insider-Transaktionen (letzte 90 Tage), groesste institutionelle Halter, Earnings-Beat-Historie, naechster Earnings-Termin.
- **Earnings-Call-Digest** — VADER-bewerteter Auszug aus den letzten Transcripts, mit dem positivsten und dem negativsten Satz als Quote.
- **Crypto metrics** (nur fuer Crypto-Symbole) — Marktkap-Rang, 24h-Volumen ueber alle Boersen, ATH/ATL-Distanz, Developer- und Community-Aktivitaet via CoinGecko.
- **Retail Sentiment** — kombiniertes StockTwits-/Reddit-Geraeusch der letzten 24 Stunden, gewichtet nach Message-Volumen.
- **Options flow** (US-gelistete Aktien) — Put/Call-Ratios fuer Volumen und Open Interest, ATM-implizite Volatilitaet, Top-3-Strikes pro Seite. Ein Skew-Label klassifiziert die Chain als bullish / bearish / neutral.
- **Macro context** — VIX, 10-jaehrige Treasury-Rendite, US-Dollar-Index und der Crypto-Fear-and-Greed-Index. Der "Wetterbericht", in dem du jedes Per-Symbol-Signal lesen solltest.
- **Sector relative strength** — Trailing-Return-Spread vs SPY, QQQ, IWM und den passenden Sektor-ETF (XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLB, XLU, XLRE, XLC). Plus 90-Tage-Korrelation und Beta vs SPY. Positives Alpha = das Symbol fuehrt seine Peers; hohes Beta = es verstaerkt SPY-Bewegungen.
- **SEC filings** — EDGAR-Filings-Index ueber FMP, klassifiziert in annual (10-K), quarterly (10-Q), material events (8-K), Proxy-Statements (DEF 14A), Offerings und Insider-Forms. Jeder Eintrag verlinkt direkt zum SEC-Dokument. Der "letztes 8-K"-Zeitstempel ist ein grober Frische-Indikator fuer Material-News, die es noch nicht in den News-Feed geschafft haben.
- **Events** — Earnings-Termine, Dividenden, Splits.
- **Holdings** — fuer ETFs: Top-Holdings mit Gewichtung.
- **News** — aggregierte News mit VADER-Sentiment pro Item.

## Wie Empfehlungen gegated werden

Eine Buy-Empfehlung ist nur dann "actionable", wenn der projizierte NETTO-Return nach Broker-Gebuehren und Kapitalertragssteuer dein `min_target_yield` ueberschreitet. Die Yield-Aufschluesselungskarte zeigt gross / fees / tax / net.
