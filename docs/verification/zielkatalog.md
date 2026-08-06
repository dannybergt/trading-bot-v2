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
| TBV2-Z01 | Jede Empfehlung kombiniert Fundamentaldaten, News/Sentiment, Markttrends, technische Analyse und ein KI-Modell (`project-plan.md:23-28`) | Die Composite-Karte weist alle vier Achsen mit Gewicht aus; eine Achse ohne Daten ist als **nicht verfuegbar** gekennzeichnet, ihr Gewicht wird nicht still umverteilt | L1+L2 | Unit: `test_composite_score.py::test_effective_weight_is_exported_and_zero_for_missing_axes` + `::test_coverage_reports_the_share_of_available_signal`. **Am laufenden Artefakt weiter unbewiesen:** `services.py` unterdrueckt den Composite auf dem synthetischen Pfad, die Karte rendert in der Regressionsumgebung gar nicht (s. Luecken) | Negativkontrolle gefahren 2026-08-05: gegen den alten Stand fallen drei Tests (kein `effectiveWeight`, keine Daempfung, keine Abdeckung) | Kern |
| TBV2-Z02 | Jede Vorhersage zeigt P(UP) und P(DOWN) explizit, plus Top-Features und Kategorie-Beitraege (`project-plan.md:29`) | Auf `/analysis/<symbol>` stehen beide Wahrscheinlichkeiten mit Einheit sichtbar, Summe 100 %, dazu die Top-Features | L2 | ui-regression: `ui_prediction_probabilities` — prueft **beidseitig**: ohne Providerzugang darf keine Wahrscheinlichkeit stehen, mit Providerzugang muessen beide da sein und sich zu 100 % ergaenzen | Der Schritt **ist** die Negativkontrolle fuer den synthetischen Fall. Belegt 2026-08-05: vor dem Fix stand dort P(UP) 100 % **und** P(DOWN) 100 % gleichzeitig | Kern |
| TBV2-Z03 | Net-Yield-Gate: handelbar nur, wenn der Netto-Ertrag nach Round-Trip-Gebuehren und Kapitalertragssteuer `min_target_yield` erreicht (`project-plan.md:30`) | Eine Order unterhalb der Schwelle wird serverseitig abgelehnt, mit nachvollziehbarer Begruendung | L1 | api-regression: `paper trading net yield gate reject` **und** `paper trading net yield gate accept` | Beide Richtungen gefahren: die Ablehnung beweist das Gate, die Annahme (Gebuehr 0, Steuer 0, 2 % gegen 1 % Mindestertrag) beweist, dass es nicht **jede** Order mit Ziel ablehnt. Die Positivkontrolle stand bis 2026-08-06 nur im Katalog und in keinem Harnisch — gefunden im Verifikationslauf | Kern |
| TBV2-Z04 | First-Login-Wizard fragt alle fuer Empfehlung und Auto-Trading noetigen Werte direkt nach Registrierung ab (`project-plan.md:31`) | Registrierung landet im Wizard; die Pflichtwerte (Broker, Gebuehren, Min-Yield, Steuern, MFA) sind dort erreichbar | L2 | ui-regression: `ui_register_submit_to_onboarding`, `ui_onboarding_wizard` | `ui_onboarding_wizard` prueft bereits, dass Artefakt-Schritte **nicht** vorzeitig gruen sind | Kern |
| TBV2-Z05 | Dashboard-Onboarding-Karte zeigt Fortschritt N/M mit Click-through und verschwindet erst bei vollstaendiger Konfiguration (`project-plan.md:32`) | Karte zeigt eine Zahl N von M; Klick fuehrt zum naechsten offenen Schritt; bei Vollkonfiguration ist sie weg | L2+L3 | ui-regression: `ui_onboarding_progress` — liest N/M aus der Karte, klickt sie durch, **stellt die Vollkonfiguration selbst her** (§4 Phase 4: die Bedingung herstellen, nicht unterstellen) und prueft die Abwesenheit ueber ein Zeitfenster von 6 s, plus Gegenprobe gegen die Einstellungen | Negativkontrolle gefahren 2026-08-05: mit dem alten `isComplete` faellt der Schritt und zitiert die Karte ("2 / 4 configured"). **Befund 2026-08-06 (WIDERLEGT, behoben):** die Karte zeigte "1 / 4" und verschwand bei "2 / 4" — Zahl und Verschwinden zaehlten Verschiedenes. N/M zaehlt jetzt die Pflichtschritte, der Beweisschritt prueft die Kohaerenz mit | Kern |
| TBV2-Z06 | Erklaerbarkeit ist Kern: jede Zone, jeder Confidence-Wert, jede Empfehlung ist auf ihre Quellen zurueckfuehrbar (`project-plan.md:33`) | **Operationalisiert 2026-08-05 (Nutzerentscheid, alle vier Lesarten):** (a) die Composite-Karte nennt je Achse Rohwert, konfiguriertes **und** wirksames Gewicht; (b) jede angezeigte Kennzahl nennt Provider und Zeitstempel; (c) das Net-Yield-Feld zeigt seine Bestandteile einzeln mit Einheit und Vorzeichen; (d) eine **abgelehnte** Automatik-Empfehlung nennt das ausloesende Gate einzeln | L2 | (a) umgesetzt (`effectiveWeight`, `coverage`, `rawConfidence`) — Beweisschritt am Artefakt offen, s. Z01. (c) gebaut, **ohne Beweisschritt**. (d) gebaut **und belegt**: ui-regression `ui_trade_gates` weist zurueck, was als roher Code statt als Satz ankommt. (b) **gebaut 2026-08-06**: jede Kennzahlen-Sektion der Analyse-Seite traegt einen sichtbaren Herkunftshinweis aus `app/metric_sources.py` — Anbieter plus Zeitpunkt **mit dessen Bedeutung** (Datenstand / abgerufen / Modell trainiert). Wo ein Anbieter keinen Zeitpunkt liefert, steht "Zeitpunkt unbekannt" statt einer erfundenen Zahl (Regel K). **Grenze, ausdruecklich:** fuer die Stammdaten-Kette, die Optionskette und die Sektor-Relativstaerke ist der genannte Zeitpunkt der **Abruf**, nicht der Datenstand — diese Anbieter datieren ihre Werte nicht | ui-regression: `ui_metric_sources` (jede Sektion traegt einen Hinweis; die genannten Anbieter werden gegen `/api/data-quality` gehalten, damit der sichtbare Text nicht im Frontend erfunden sein kann); Unit: `test_metric_sources.py` (Sektion ohne Hinweis, unbekannter Schluessel, Zeitstempel ohne Bedeutung, Widerspruch zur Vertrauensnote). Negativkontrollen gefahren 2026-08-06: Hinweis entfernt -> 2 rot mit Nennung der Sektion; `available` geloegen -> 2 rot mit Zitat beider Aussagen; Bedeutung entfernt -> 1 rot mit Nennung des Schluessels | Kern |
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
| TBV2-Z14 | Doku spiegelt den Stand (`project-plan.md:34`) | Prozesskriterium, kein Laufzeitverhalten — geprueft ueber die DoD im PR, nicht am laufenden System | n/a (strukturell) | §5 DoD | Erweiterung |

## Bekannte Luecken

### Stand 2026-08-05, nach der Welle "leichter, benutzerfreundlicher, funktionaler"

Von den vier Kernzeilen ohne Beweisschritt sind **zwei geschlossen** (Z02 und Z05, beide mit
gefahrener Negativkontrolle), eine ist **operationalisiert, aber erst zu einem Viertel gebaut**
(Z06), und eine bleibt **strukturell unbeweisbar in dieser Umgebung** (Z01, s. unten).

Der Konsolen-Mitschnitt der ui-regression ist damit ebenfalls geschlossen: `ui_console_clean`
sammelt `Runtime.exceptionThrown` und `Runtime.consoleAPICalled` ueber den gesamten Durchlauf und
**bricht ab**, statt nur zu protokollieren. Unterdrueckt wird ausschliesslich Umgebungsrauschen,
und die Zahl der unterdrueckten Meldungen steht in der Erfolgszeile — ein wachsender Filter faellt
damit auf, statt still zu wachsen. Erster Lauf: **0 Meldungen ueberhaupt**.

Offen bleibt der umgekehrte Befund: **43 von 75 Harnisch-Schritten bewachen keine Zielzeile.**
`ui_guided_tour_tracks_real_data` und `admin audit-events list` gehoeren in den Katalog.

### Die Regressionsumgebung erreicht keine Provider

Belegt im ersten Lauf am 2026-08-05: `data quality price history coheres with the chart ok
[synthetic placeholder (181 bars) — no provider reachable from this host]`. Das hat eine
unbequeme Folge, die hier stehen bleibt, statt in einem gruenen Haken zu verschwinden:

Der erste Entwurf dieses Schrittes behauptete nur `price_history != "missing"`. Diese Assertion
haette **auch mit dem kaputten Grader bestanden** — der synthetische Pfad war genau der, den der
alte Code korrekt bewertete. Ein Beweisschritt ohne Trennschaerfe ist kein Beweis (Sperre 2). Der
Schritt prueft jetzt die Kohaerenz zwischen Chart-Endpunkt und Bewertung und **druckt den
beobachteten Modus mit**, damit ein providerloser Lauf sichtbar ist, statt still durchzugehen.

**Konsequenz fuer TBV2-Z01:** `services.py` unterdrueckt den Composite auf dem synthetischen Pfad
(`if not used_synthetic`), die Composite-Karte rendert in dieser Umgebung also **gar nicht**. Das
wirksame Achsengewicht ist damit auf Unit-Ebene belegt und am laufenden Artefakt unbewiesen. Z01
bleibt `NICHT PRUEFBAR (kein Provider-Zugang in der Regressionsumgebung)`.

**Fuer TBV2-Z02 gilt das Umgekehrte:** dort ist die Providerlosigkeit ein Vorteil, weil sie genau
den synthetischen Fall herstellt, in dem sich die Anzeige selbst widersprach. Der Realdatenzweig
des Schrittes ist in dieser Umgebung nie gelaufen und erreicht `NACHGEWIESEN` erst ueber Stufe 3.

**Fuer TBV2-Z07** unveraendert: der Realdatenfall ist hier strukturell nicht beweisbar, bis dahin
gilt `NICHT PRUEFBAR` — nicht `NACHGEWIESEN`.
