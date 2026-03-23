# Benutzerhandbuch

## Was das Tool bietet

- Login und Benutzerverwaltung
- optionales MFA
- Watchlists fuer beobachtete Werte
- Watchlist-Tags fuer thematische Einordnung wie `swing`, `priority` oder `crypto`
- Marktanalyse und Scanner
- Suche nach Ticker, ISIN und WKN
- Assetklassifizierung fuer Stocks, ETFs und Krypto in Suche, Scanner und Analyse
- aggregierte Watchlist-News-Bindung mit Sentiment pro beobachtetem Wert
- priorisierter Watchlist-Alert-Feed mit Signal-, News- und Tag-Kontext
- Alpaca-Kontodaten, Orders, Positionen und Historie
- Push-Benachrichtigungen fuer starke Signale

## Aktueller Stand

Dieser lokale Stand wurde aus Docker-Images rekonstruiert. Das Backend ist als Quellcode verfuegbar. Vom Frontend liegt derzeit nur das gebaute Web-Bundle vor.

## Nutzung lokal

1. Administrator startet den Stack.
2. Benutzer registriert sich oder wird durch einen Admin angelegt.
3. Benutzer hinterlegt optional Alpaca-Zugangsdaten.
4. Benutzer pflegt Watchlists, versieht Eintraege mit Tags und analysiert Werte.
5. Benutzer aktiviert bei Bedarf MFA und Push.

## Wichtige Grenze

Analyse- und Trading-Signale sind kein verlaesslicher Handelsrat. Das System nutzt externe Datenquellen, heuristische Indikatoren und ML-Komponenten mit moeglichen Fehlbewertungen.
