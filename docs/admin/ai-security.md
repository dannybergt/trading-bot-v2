# AI Security

## Relevanz

Das Produkt nutzt zwar kein LLM im extrahierten Stand, aber es erzeugt algorithmische Handels- und Alerting-Entscheidungen auf Basis untrusted Marktdaten, News-Texten und externer APIs. Dafuer gelten aehnliche Schutzprinzipien wie fuer agentische Systeme.

## Untrusted Inputs

- News-Inhalte aus externen Quellen
- Symbole, ISIN, WKN und Suchanfragen von Nutzern
- Markt- und Historienfeeds von Alpaca und yfinance
- Browser-Push-Subscriptions

## Risiken

- manipulierte oder verrauschte News koennen Analyse und Alerts verzerren
- teure Analysepfade koennen fuer DoS missbraucht werden
- unscharfe Fehlertoleranz kann falsche Handlungssignale als valide erscheinen lassen
- Trading-Aktionen duerfen nie allein aus unsicherer Modell- oder Drittquellenlogik erfolgen

## Kontrollen

- externe Daten strikt als Daten, nie als Instruktionen behandeln
- Alerts und Orders serverseitig an harte Plausibilitaets- und Policy-Pruefungen koppeln
- Nutzerkontext und globale Scannerlogik sauber trennen
- Modellprognosen als Assistenzsignal kennzeichnen, nicht als autonomes Order-Signal
- Audit-Logging fuer Orderausloesung, Push und kritische Kontoaktionen einfuehren
