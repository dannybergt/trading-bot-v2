<!-- page: / -->
# Dashboard

Das Dashboard ist die zentrale Landing-Flaeche fuer alles, was du beobachtest, und alles, was gerade deine Aufmerksamkeit braucht.

## Was du siehst

- **Setup-Progress-Karte** — oben auf der Seite, wird nur angezeigt, solange noch Onboarding-Schritte offen sind. Verlinkt in den Wizard fuer alles, was noch fehlt (Broker-Keys, Gebuehren, Steuersatz, MFA).
- **Aktive-Watchlist-Auswahl** — jede andere Sektion folgt dieser Auswahl.
- **Tracked assets** — jedes Symbol der aktiven Watchlist mit Asset-Klasse (Stock / ETF / Crypto), Tags und einem direkten Link zur Analyse-Seite.
- **Provider coverage** — kleine KPI-Karten, die zaehlen, wie viele deiner beobachteten Symbole Live-Daten, Teilabdeckung oder gar keine Daten haben. Hilfreich wenn etwas "leer" wirkt: zeigt, ob ein Provider stumm ist oder du in der Asset-Klasse einfach nichts trackst.
- **Watchlist alerts** — nach Prioritaet sortierte Liste handelsrelevanter Eintraege aus deiner Alert-Konfiguration.
- **Macro calendar** — aktuelle 10Y-/2Y-Treasury-Renditen und der 10Y-2Y-Spread (mit Inverted-Badge bei invertierter Kurve) plus die naechsten fuenf geplanten FRED-Release-Termine (CPI, NFP/Employment Situation, FOMC, GDP, PCE). Erfordert `FRED_API_KEY` in `.env.local`. Phase-4-Auto-Execution nutzt diese Termine als Halt-Trigger.
- **News ticker** — rollende Schlagzeilen fuer die aktive Watchlist; jeder Eintrag verlinkt auf die Quelle.

## Wie es aktualisiert

Die Watchlist-Alerts refreshen ungefaehr im Minutentakt. News, Tracked Assets und Provider Coverage werden separat gecacht, damit der langsamere Alert-Pfad sie nicht blockiert — beim Cold Load erscheinen sie in Etappen.

## Haeufige Aktionen

- **Watchlist anlegen oder umbenennen** → die [Watchlists-Seite](/watchlists).
- **Einzelnes Symbol untersuchen** → klicke das Symbol in einer Tracked-Assets-Karte.
- **Alerts konfigurieren** → [Alerts](/alerts) fuer Regel-CRUD.
