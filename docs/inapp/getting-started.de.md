<!-- page: /docs -->
# Erste Schritte

Das ist der Einstieg in die In-App-Dokumentation. Waehle ein Thema in der Seitenleiste oder oeffne auf jeder Seite den kontextuellen Help-Drawer (Button **?** im Header) fuer eine Kurzfassung plus Link zurueck hierher.

## Empfohlene Lesereihenfolge

1. **[Dashboard](/docs/dashboard)** — was du nach dem Login siehst und wie die Flaechen zusammenhaengen.
2. **[Watchlists](/docs/watchlists)** — das Symbol-Universum, das jede andere Sicht treibt.
3. **[Symbol-Analyse](/docs/analysis)** — alle Signale, die wir pro Ticker holen.
4. **[Paper Trading](/docs/paper-trading)** — simulierte Orders, das Net-Yield-Gate und das Trade-Journal.
5. **[Alerts](/docs/alerts)** — persistente Regeln und wie sie feuern.
6. **[Settings](/docs/settings)** — Broker-Keys, Gebuehren, Steuern, MFA.
7. **[Administration](/docs/admin)** — nur relevant, wenn deine Rolle Admin ist.

## Wie Empfehlungen entstehen

Jede Per-Symbol-Empfehlung kombiniert fuenf Signal-Klassen — Fundamentals, News, Trend, Technical, AI — zu einer wahrscheinlichkeitsgewichteten Prediction. Das Modell flagt eine Buy/Sell-Empfehlung erst als "actionable", wenn der projizierte NETTO-Return nach Broker-Gebuehren und Kapitalertragssteuer dein `min_target_yield` ueberschreitet (in den [Settings](/settings) gesetzt).

## Privatsphaere

Identifizierende Werte (E-Mail-Adressen, IPs, User-Agents) im Audit-Log werden als Einweg-SHA-256-Fingerprints gespeichert. Broker-Secrets sind at-rest verschluesselt. Backups tragen die Fingerprints, niemals Klartext-PII.
