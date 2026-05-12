<!-- page: /settings -->
# Settings

Persoenliche Kontokonfiguration. Die Werte hier treiben jede Empfehlung und jeden Paper-Trading-Fill.

## Sektionen

- **Profil** — read-only Zusammenfassung deiner E-Mail, Rolle und Onboarding-Status.
- **Alpaca-Broker** — API-Key, Secret-Key, Paper-/Live-Toggle. Pflicht, bevor die Broker-gestuetzten Flaechen (Konto-Sicht, Positionen, spaeter echte Orders) funktionieren.
- **Portfolio-Defaults** — Broker-Gebuehrenmodell und Mindest-Netto-Yield:
  - **trade_fee_absolute** — flache Gebuehr pro Leg in Kontowaehrung
  - **trade_fee_percent** — Prozent-Gebuehr auf Gross-Notional pro Leg
  - **min_target_yield** — minimaler NETTO-Return in Prozent (nach Gebuehren und Kapitalertragssteuer), damit eine Empfehlung "actionable" zaehlt
  - **capital_gains_tax_bps** — Abgeltungssteuer / Kapitalertragssteuer in Basispunkten (z.B. 26375 = 26.375 Prozent)
  - **income_tax_bps** — Fallback-Einkommenssteuer-Satz fuer Jurisdiktionen, die kurzfristige Gewinne als Lohneinkommen versteuern
- **Multi-Faktor-Authentifizierung** — Drei-Schritte-Lifecycle: Setup (generiert Secret + Provisioning-URI), Enable (verifiziert Code aus dem Authenticator), Disable (braucht ebenfalls einen aktuellen Code).

## Wo die Werte genutzt werden

- Der Mindest-Yield ist das Gate, das die Empfehlungs-Karte und die Paper-Trading-Order-Annahme beide pruefen.
- Das Gebuehrenmodell wird auf jeden Paper-Trading-Fill angewandt.
- Der Steuersatz wird nur auf realisierten Gewinn angewandt.
- Alpaca-Keys werden at-rest mit `APP_ENCRYPTION_KEY` verschluesselt und nie im Klartext zurueckgegeben.

## Audit-Trail

Jede Aenderung an Alpaca-Konfig oder Portfolio-Defaults erzeugt einen `audit_events`-Eintrag, sichtbar fuer Admins unter [Admin → Audit](/admin). Identifizierende Werte werden als Fingerprints gespeichert, nicht im Klartext.
