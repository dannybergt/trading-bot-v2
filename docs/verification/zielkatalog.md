# Zielkatalog — trading-bot-v2

Das fixierte Ziel, gegen das der `verifier` nachweist, ob das Produkt tut, was es verspricht.
Verfahren: globale `verify`-Skill (Phasen 0-8). Massstab: globaler `verifier`-Agent.

**Wozu diese Datei existiert.** Am 2026-08-05 lief die komplette Gate-Kette gruen, waehrend die
Analyse-Seite live "PRICE HISTORY: missing" neben einem vollstaendig gerenderten Kurschart
zeigte. Gruen war belegt, das Ziel nicht. Ohne fixierten Massstab ist "vollstaendig
nachgewiesen" keine Aussage, sondern Ermessen.

**Eigentum.** Der Mensch besitzt `Zielsatz` und `Stufe` — was wir versprechen. Der Agent besitzt
`Beweisschritt`, `Negativkontrolle` und `Status` — wie wir es belegen. Der Agent schreibt diese
Datei nicht selbst; er schlaegt vor, der Mensch entscheidet.

**IDs sind append-only.** Eine zurueckgezogene Zeile bleibt stehen und bekommt
`Status: zurueckgezogen (ADR-<datum>)`. Nie wiederverwenden, nie loeschen.

## Urteilswerte

`NACHGEWIESEN` am laufenden Artefakt beobachtet, mit Beleg und bestandener Negativkontrolle ·
`BEHAUPTET` nur Test gruen · `NICHT PRUEFBAR` mit Grund · `WIDERLEGT` · `n/a (strukturell)`.
Nur `n/a (strukturell)` blockiert **nicht**.

## Kernkriterien

Quelle der Zielsaetze: `docs/admin/project-plan.md` Sektion "Produktvision" (verbindlich laut
`CLAUDE.md`) und die dortige UX-Direktive.

| ID | Zielsatz (Quelle) | Beobachtbares Kriterium | Schicht | Beweisschritt | Negativkontrolle | Stufe |
|---|---|---|---|---|---|---|
| TBV2-Z01 | Jede Empfehlung kombiniert Fundamentaldaten, News/Sentiment, Markttrends, technische Analyse und ein KI-Modell (`project-plan.md:21-26`) | Die Composite-Karte weist alle vier Achsen mit Gewicht aus; eine Achse ohne Daten ist als **nicht verfuegbar** gekennzeichnet, ihr Gewicht wird nicht still umverteilt | L1+L2 | `ui_analysis` **reicht nicht** — prueft nur Symbolname + Chart-Element. **Beweisschritt fehlt** | Symbol ohne Fundamentaldaten (Krypto) muss die Achse als n/a zeigen, nicht als 0 | Kern |
| TBV2-Z02 | Jede Vorhersage zeigt P(UP) und P(DOWN) explizit, plus Top-Features und Kategorie-Beitraege (`project-plan.md:27`) | Auf `/analysis/<symbol>` stehen beide Wahrscheinlichkeiten mit Einheit sichtbar, Summe 100 %, dazu die Top-Features | L2 | **Beweisschritt fehlt** — kein Harnisch-Schritt prueft die Wahrscheinlichkeiten | Synthetischer Datenpfad darf keine Wahrscheinlichkeit als belastbar ausweisen | Kern |
| TBV2-Z03 | Net-Yield-Gate: handelbar nur, wenn der Netto-Ertrag nach Round-Trip-Gebuehren und Kapitalertragssteuer `min_target_yield` erreicht (`project-plan.md:28`) | Eine Order unterhalb der Schwelle wird serverseitig abgelehnt, mit nachvollziehbarer Begruendung | L1 | api-regression: `paper trading net yield gate reject` | Der Schritt **ist** die Negativkontrolle — er beweist die Ablehnung. Ergaenzend: Gebuehr senken ⇒ dieselbe Order muss durchgehen | Kern |
| TBV2-Z04 | First-Login-Wizard fragt alle fuer Empfehlung und Auto-Trading noetigen Werte direkt nach Registrierung ab (`project-plan.md:29`) | Registrierung landet im Wizard; die Pflichtwerte (Broker, Gebuehren, Min-Yield, Steuern, MFA) sind dort erreichbar | L2 | ui-regression: `ui_register_submit_to_onboarding`, `ui_onboarding_wizard` | `ui_onboarding_wizard` prueft bereits, dass Artefakt-Schritte **nicht** vorzeitig gruen sind | Kern |
| TBV2-Z05 | Dashboard-Onboarding-Karte zeigt Fortschritt N/M mit Click-through und verschwindet erst bei vollstaendiger Konfiguration (`project-plan.md:30`) | Karte zeigt eine Zahl N von M; Klick fuehrt zum naechsten offenen Schritt; bei Vollkonfiguration ist sie weg | L2+L3 | ui-regression: `ui_dashboard` deckt **nur** die Existenz von "Setup progress" ab. N/M, Click-through und Verschwinden: **Beweisschritt fehlt** | Vollstaendig konfigurierter Nutzer darf die Karte nicht mehr sehen | Kern |
| TBV2-Z06 | Erklaerbarkeit ist Kern: jede Zone, jeder Confidence-Wert, jede Empfehlung ist auf ihre Quellen zurueckfuehrbar (`project-plan.md:31`) | **OFFEN — Mensch entscheidet.** Vorschlaege: (a) jede angezeigte Kennzahl hat ein Quellen-Tooltip; (b) die Composite-Karte nennt je Achse den Rohwert und das Gewicht; (c) das Net-Yield-Feld zeigt seine Bestandteile einzeln | L2 | offen bis zur Operationalisierung | offen | Kern |
| TBV2-Z07 | Empfehlung und Anzeige widersprechen sich nie (Regel K; ADR 2026-08-05) | Ein Zustandswort und der Inhalt daneben passen zusammen: voller Chart ⇒ `price_history` nicht `missing`; synthetische Balken ⇒ `fallback`; leere Daten ⇒ kein belastbarer Verdict | L1+L2 | api-regression: `data quality price history coheres with the chart` — **prueft die Kohaerenz, nicht einen festen Wert**, und druckt den beobachteten Modus mit. **Einschraenkung:** auf einem Host ohne Provider-Zugang laeuft er im synthetischen Modus und hat dort **keine** Trennschaerfe fuer den Realdatenfall (s. Luecken) | Unit-Ebene belegt gefahren: mit dem alten Grader fallen drei Tests rot (`'missing' != 'full'`). Realdatenfall nur ueber Stufe 3 belegbar | Kern |
| TBV2-Z08 | Oberflaeche ist DE/EN parallel, Auswahl persistiert (`CLAUDE.md` UX-Direktive) | Bei Sprache=Deutsch sind die Ueberschriften uebersetzt und ueberleben einen Reload | L2 | ui-regression: `ui_i18n_german`; Struktur: `test_i18n_bundles.py` | Entfernter Key laesst zwei Tests rot werden und nennt den Pfad (belegt 2026-07-28) | Kern |
| TBV2-Z09 | Der ausgelieferte Stand ist erkennbar (ADR 2026-07-28) | Das Badge zeigt die Version einfach praefigiert, unter der Karte, uebereinstimmend mit `/api/version` | L1+L2 | ui-regression: `ui_version_badge`; api-regression: `version` | Negativkontrolle gefahren 2026-07-28 unter reparierter Harness | Kern |
| TBV2-Z10 | Daten ueberleben Upgrade und Restore (`project-plan.md:322` Entscheidungsregel) | Migration vorwaerts auf einer DB-Kopie, Backup/Restore in einen frischen Stack, Daten vollstaendig | L3 | `tests/run-upgrade-rehearsal.sh` | Rehearsal faehrt zwei getrennte Stacks und vergleicht — der Vergleich ist die Kontrolle | Kern |
| TBV2-Z11 | Geschuetzte Funktionen sind serverseitig geschuetzt (§6.2) | Ohne Token 401; Rate-Limit greift auch hinter dem Reverse-Proxy | L1 | api-regression: `forwarded-for scopes auth rate limit` | Negativkontrolle ueber `FORWARDED_ALLOW_IPS=127.0.0.1` bereits im Harnisch vorgesehen | Kern |

## Erweiterungen

| ID | Zielsatz | Kriterium | Schicht | Beweisschritt | Stufe |
|---|---|---|---|---|---|
| TBV2-Z12 | Bedienbar auch auf Telefonbreite | Kein horizontaler Overflow bei 390/1280/1920 px, Nav kollabiert unter `lg` | L2 | `ui_responsive_shell`, `ui_mobile_nav` | Erweiterung |
| TBV2-Z13 | Die deployte Instanz entspricht dem geprueften Stand | Live-Sonde ohne Befund, Badge deckt sich mit `/api/version` | L1+L2 | `node tests/run-live-ui-smoke.mjs` (Stufe 3) | Erweiterung |
| TBV2-Z14 | Doku spiegelt den Stand (`project-plan.md:33`) | Prozesskriterium, kein Laufzeitverhalten — geprueft ueber die DoD im PR, nicht am laufenden System | n/a (strukturell) | §5 DoD | Erweiterung |

## Bekannte Luecken (Stand 2026-08-05, vor dem ersten Lauf)

Vier Kernzeilen haben **keinen** Beweisschritt: TBV2-Z01 (Achsen-Ausweisung), TBV2-Z02
(Wahrscheinlichkeiten), TBV2-Z05 (N/M, Click-through, Verschwinden) und TBV2-Z06 (offen bis zur
Operationalisierung). Das ist kein Versaeumnis dieses Katalogs, sondern sein erster Ertrag: die
Suite hat 21 UI-Schritte und ~52 API-Schritte, aber **keiner** davon prueft die
Wahrscheinlichkeitsdarstellung, die laut Produktvision Punkt 2 verbindlich ist.

Umgekehrter Befund (Beweisschritte ohne Zielzeile) gehoert in denselben Bericht, sobald der
erste vollstaendige Lauf gefahren ist.

### Die Regressionsumgebung erreicht keine Provider

Belegt im ersten Lauf am 2026-08-05: `data quality price history coheres with the chart ok
[synthetic placeholder (181 bars) — no provider reachable from this host]`. Das hat eine
unbequeme Folge, die hier stehen bleibt, statt in einem gruenen Haken zu verschwinden:

Der erste Entwurf dieses Schrittes behauptete nur `price_history != "missing"`. Diese Assertion
haette **auch mit dem kaputten Grader bestanden** — der synthetische Pfad war genau der, den der
alte Code korrekt bewertete. Ein Beweisschritt ohne Trennschaerfe ist kein Beweis (Sperre 2). Der
Schritt prueft jetzt die Kohaerenz zwischen Chart-Endpunkt und Bewertung und **druckt den
beobachteten Modus mit**, damit ein providerloser Lauf sichtbar ist, statt still durchzugehen.

**Konsequenz fuer TBV2-Z01, TBV2-Z02 und TBV2-Z07:** der Realdatenfall ist in der
Regressionsumgebung strukturell nicht beweisbar. Diese Zeilen erreichen `NACHGEWIESEN` nur ueber
**Stufe 3** gegen die deployte Instanz. Bis dahin gilt fuer den Realdatenpfad `NICHT PRUEFBAR
(kein Provider-Zugang in der Regressionsumgebung)` — nicht `NACHGEWIESEN`.
