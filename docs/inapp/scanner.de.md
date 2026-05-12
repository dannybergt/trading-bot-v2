<!-- page: /scanner -->
# Scanner

Der Scanner zieht die heutige Marktbewegung fuer jedes Symbol der aktiven Watchlist und sortiert nach absoluter Veraenderung. Schneller Weg, "was bewegt sich gerade in meinem Universum" zu sehen.

## Was du siehst

- **Sortierbare Liste** deiner Watchlist-Symbole mit aktuellem Preis, Tages-Veraenderung in Prozent und Asset-Klassen-Label.
- **Provider-Status-Pillen** — gruen, wenn der Provider eine Live-Quote zurueckgegeben hat; gelb fuer Teilabdeckung; grau, wenn kein Provider geantwortet hat.
- **Asset-Mix-Aufschluesselung** oben — wie viele Stocks, ETFs und Crypto-Symbole du trackst.

## Warum Werte fehlen koennen

- yfinance throttled gelegentlich; die Zelle zeigt "—", bis der naechste Refresh klappt.
- Crypto-Symbole nutzen den Alpha-Vantage-Pfad; wenn `ALPHA_VANTAGE_API_KEY` nicht konfiguriert ist, bleibt die Zelle leer.
- Nicht-US-Symbole fallen auf Twelve Data zurueck; ist das auch nicht konfiguriert, bleibt die Zeile leer, bis mindestens ein Provider antwortet.

## Haeufige Aktionen

- **Analyse oeffnen** fuer ein Symbol per Klick auf die Zeile. Bringt dich zur vollstaendigen Single-Symbol-Sicht.
- **Neues Symbol hinzufuegen** — zurueck zu [Watchlists](/watchlists). Der Scanner zieht es beim naechsten Refresh automatisch.
