<!-- page: /paper-trading -->
# Paper Trading

Setze simulierte Orders gegen dein Watchlist-Universum. Fills laufen gegen den letzten Close mit Asset-klassen-spezifischer Slippage, und ein Net-Yield-Gate weist Orders ab, deren Mindest-Yield nach Gebuehren und Kapitalertragssteuer nicht erreicht wird.

## Tabs

- **Open orders** — pending Limit-Orders, die warten, dass der Markt das Limit kreuzt. Der Background-Fill-Task bewertet sie alle drei Minuten neu.
- **Trade journal** — chronologische Liste jedes Fills mit Stueckzahl, Preis, Gebuehren, Kapitalertragssteuer sowie nominalem und prozentualem realisiertem P&L.
- **Positions** — aktuelle offene Positionen mit Durchschnittseintrittspreis, letztem Preis, unrealisiertem P&L, plus Gebuehren- und Steuer-Summen pro Position.
- **Summary** — Summen ueber alle Transaktionen: realisierter P&L, unrealisierter P&L, Gebuehren-Summe, Steuer-Summe, offene Exposure, Transaktions-Count.

## Wie Fills funktionieren

- **Market-Orders** — fuellen sofort zum letzten Close mit adverser Slippage (Stock 0.1 Prozent, ETF 0.05 Prozent, Crypto 0.3 Prozent, hochskaliert mit Position-Size relativ zum 20-Tage-Durchschnittsvolumen, gedeckelt bei 1 Prozent).
- **Limit-Orders** — fuellen, wenn der letzte Close das Limit kreuzt. Sie bleiben "open", bis sie fuellen oder du canceln.

## Wie Gebuehren und Steuern funktionieren

Deine Broker-Gebuehren kommen aus den Portfolio-Defaults unter Settings. Der Simulator wendet zusaetzlich einen Asset-Klassen-Gebuehren-Multiplikator an: Stock und ETF mit 1x, Crypto mit 5x — abbildend, was Coinbase/Binance typischerweise nehmen. Kapitalertragssteuer wird nur auf realisierten Gewinn angewandt.

## Net-Yield-Gate

Wenn du (oder die Empfehlungskarte) einen Zielpreis lieferst, berechnet das Gate den Netto-Ziel-Prozentsatz nach Gebuehren und Steuern. Orders unter deinem `min_target_yield` werden mit einer Aufschluesselung von gross / fees / tax / net abgelehnt, damit du entscheiden kannst, ob du manuell ueberschreiben willst.

## Auto vs manuell

- **manual** — du fuellst das Formular selbst. Das Gate feuert nur, wenn du einen Zielpreis angegeben hast.
- **auto-recommendation** — die Order wurde ueber den Link "Place paper order at this target" auf der Analyse-Seite erzeugt. Der Source-Wert wird in den Audit-Log durchgereicht.
