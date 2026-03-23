# Sitzungslog

- Datum: 2026-03-23
  Kontext: Git-Sync und Docker-Hub-Sync sollen kuenftig ohne manuellen Nachlauf passieren.
  Erledigt: Git-Remote laeuft jetzt lokal ueber SSH; `.github/workflows/publish.yml` publiziert auf jedem Push nach `main` automatisch `latest` plus `sha-<commit>` fuer Backend und Frontend und publiziert auf Git-Tags `v*` weiterhin den entsprechenden Release-Tag; `README.md`, `docs/admin/release.md` und `state/decisions.md` dokumentieren den neuen Automatikpfad und die dafuer benoetigten Docker-Hub-Secrets.
  Offen: Der neue GitHub-Actions-Pfad sollte nach dem naechsten echten `main`-Push einmal im Runner beobachtet werden, damit der automatische Docker-Hub-Sync mit den hinterlegten Secrets auch live bestaetigt ist.

- Datum: 2026-03-23
  Kontext: Die lokale Git-Anbindung des rekonstruierten Projekts soll an das vorhandene GitHub-Repository angeschlossen werden.
  Erledigt: Lokales Repository unter `/codex/trading-bot-v2` ist vorhanden; `origin` zeigt auf `https://github.com/dannybergt/trading-bot-v2.git`; das Remote-Repository war leer und wurde nun mit dem lokalen Initial-Commit `93cc39c` befuellt; `main` trackt jetzt sauber `origin/main`; der initiale Token ohne Workflow-Berechtigung wurde serverseitig abgewiesen, danach wurde mit einem Token inklusive Workflow-Recht der Push erfolgreich wiederholt; die temporaere Token-Datei `/tmp/github-token` wurde anschliessend wieder entfernt.
  Offen: Keine unmittelbaren Git-Anbindungsblocker mehr.

- Datum: 2026-03-23
  Kontext: Arbeitsmodus fuer dieses Repository konkretisiert.
  Erledigt: Sinnvolle Aenderungen sollen ab jetzt jeweils direkt committed und nach Moeglichkeit sofort nach `origin/main` gepusht werden.
  Offen: Pushes ueber HTTPS brauchen weiterhin eine verfuegbare GitHub-Authentifizierung auf diesem System.

- Datum: 2026-03-23
  Kontext: Der naechste fachliche Schritt soll den ETF-/Krypto-Providerpfad entlasten, damit Watchlist-Alerts nicht doppelt News/Fundamentals ziehen und ETF-Werte auch ohne sofort verfuegbare Provider-Metadaten sauber in Watchlists klassifiziert werden.
  Erledigt: `src/backend/app/services.py` cached YFinance-Fundamentals und Watchlist-News jetzt mit TTL, ueberspringt Krypto-Fundamentals komplett und erlaubt `get_stock_data(..., include_news=False, include_fundamentals=False)` fuer schlankere Alert-Pfade; `src/backend/app/main.py` nutzt diese entlastete Variante jetzt im Watchlist-Alert-Feed und im Auto-Scanner ohne unnoetige Fundamentals-Last; `src/backend/app/asset_metadata.py` kann ETFs jetzt auch aus expliziten Fallback-/Watchlist-Namen wie `Vanguard S&P 500 ETF` erkennen; neue Unit-Tests in `tests/test_market_data_service.py` pruefen Cache- und Skip-Verhalten, `tests/test_asset_metadata.py` deckt den ETF-Fallback ab, und `tests/run-api-regression.sh` validiert den erweiterten Watchlist-Pfad jetzt auch mit einem ETF-Eintrag; containerisierte Unit-Tests und die isolierte API-Regression gegen den frischen lokalen Build liefen erfolgreich.
  Offen: Der Providerpfad ist jetzt robuster und billiger, aber noch kein echter breiter ETF-/Krypto-Livefeed; naechster Produktschritt bleibt echte Providerabdeckung fuer ETFs/Krypto-News/-Bars statt nur besserer Fallback- und Cache-Strategie.

- Datum: 2026-03-23
  Kontext: Phase-1-Metadaten und Watchlist-Tags sollen im rekonstruerten Frontend sichtbar werden, ohne auf die langsamere Alert-Berechnung zu blockieren.
  Erledigt: `src/frontend-dist/ui-patches.js` erweitert das bestehende Dashboard-Panel `Watchlist Alerts` um eine `Tracked Assets`-Sektion mit Assetklassen-Mix, Top-Tags, Exchange-/Market-Metadaten und symbolbezogenen Analyse-/Trade-Drilldowns; News- und Tracked-Asset-Daten werden jetzt getrennt vom Alert-Feed gecacht und bereits im Teilzustand gerendert, damit Ticker, Asset-Mix und Tag-Summary auch bei spaeter eintreffendem `/api/watchlists/{id}/alerts` sichtbar bleiben; `tests/run-ui-regression.mjs` seedet im isolierten Stack Watchlist-Tags per API und validiert Asset-Mix, Tag-Summary und Tracked-Asset-Karten erfolgreich; der komplette UI-Lauf gegen den lokalen Build lief erfolgreich auf Alternativports `18190/18194`.
  Offen: Der Patch bleibt eine Bundle-Nachruestung; naechster sinnvoller Produktschritt ist jetzt der Live-Daten-/Providerpfad fuer ETFs und Krypto sowie spaeter die Ueberfuehrung in echten Frontend-Quellstand.

- Datum: 2026-03-20
  Kontext: Im ausgelieferten Frontend sind Dashboard-Shortcut und Alpaca-Settings-Navigation fuer Nutzer missverstaendlich.
  Erledigt: Produktions-Bundle um `src/frontend-dist/ui-patches.js` erweitert und in `index.html` eingebunden; Dashboard versieht die beiden Zahnrad-Shortcuts jetzt mit getrennten Titeln/Iconografie fuer Account Settings vs. User Administration; die Alpaca-/Settings-Seite erhaelt einen sichtbaren `Back to Dashboard`-Button mit explizitem Sprung auf `/`; `tests/run-ui-regression.mjs` prueft diese Punkte rollenbewusst, ist gegen ein Chrome-Cleanup-Race beim Entfernen des temporaeren Browserprofils gehaertet und wurde erfolgreich sowohl gegen einen bestehenden Nicht-Admin-Stack als auch im isolierten Fresh-Stack mit Admin-Shortcut validiert.
  Offen: Nach jedem kuenftigen Frontend-Image-Refresh muss validiert werden, dass der Patch weiter geladen wird oder kontrolliert in echten Frontend-Quellstand ueberfuehrt wurde.

- Datum: 2026-03-20
  Kontext: Phase 1 soll nicht nur Backend-Endpunkte liefern, sondern Watchlist-News und priorisierte Alerts sichtbar in die UI bringen.
  Erledigt: `src/frontend-dist/ui-patches.js` erweitert das rekonstruierte Bundle jetzt um ein Dashboard-Panel `Watchlist Alerts`, das die aktive Watchlist aus dem vorhandenen Select liest, `/api/watchlists/{id}/alerts` und `/api/watchlists/{id}/news` rollenbewusst nachlaedt, priorisierte Signal-/News-Kandidaten anzeigt und den unteren `Live News`-Ticker mit beobachteten Watchlist-News speist; Alert-Karten bieten jetzt Drilldown nach Analyse/Trade/Story, neue High-Priority-Alerts koennen als deduplizierte Toast-Popups auftauchen, und die Insights werden periodisch aktualisiert; `tests/run-ui-regression.mjs` validiert die neue Flaeche inklusive Drilldown-CTA im Dashboard; Low-Level-Regression gegen den Hauptstack und der isolierte Fresh-Stack-Lauf waren erfolgreich.
  Offen: Der Patch ist weiter eine Bundle-Nachruestung; mittelfristig gehoert diese UI in echten Frontend-Quellstand, inklusive echter In-App-Navigation, Popup-Alert-Management und laufender Aktualisierung ohne DOM-Patch-Layer.

- Datum: 2026-03-20
  Kontext: Es fehlt ein kontrollierter Erstzugang fuer Benutzerverwaltung und Admin-Funktionen.
  Erledigt: Startup bootstrapt jetzt optional einen initialen Admin aus `INITIAL_ADMIN_EMAIL` und `INITIAL_ADMIN_PASSWORD`; `INITIAL_ADMIN_MFA_ENABLED=false` erlaubt den ersten Login ohne MFA; API-Regression prueft den Seed-Admin-Lifecycle, und containerisierte Unit-Tests decken die Bootstrap-Logik ab.
  Offen: Im laufenden Haupt-Stack muessen noch echte Bootstrap-Credentials in `.env` gesetzt und der Stack neu gestartet werden, damit dieser Pfad ausserhalb der Tests aktiv ist.

- Datum: 2026-03-20
  Kontext: Watchlist-News nicht nur aggregieren, sondern fuer spaetere Popups und Alerts priorisiert nutzbar machen.
  Erledigt: neues Backend-Modul fuer Watchlist-Alert-Priorisierung aus Signal-, News- und Tag-Kontext eingefuehrt; Endpunkt `/api/watchlists/{id}/alerts` liefert pro beobachtetem Wert priorisierte Alert-Kandidaten mit Signal-/News-Snapshot; `ops/automation/test.sh` fuehrt jetzt host-seitige Unit-Tests aus; API-Regression prueft den neuen Alert-Feed mit.
  Offen: dieselbe Priorisierung muss spaeter ins Frontend bzw. in laufende Popup-/Ticker-Flaechen ueberfuehrt und mit belastbareren Live-News/Livedaten gespeist werden.

- Datum: 2026-03-20
  Kontext: Phase 1 nicht nur mit Metadaten beginnen, sondern Watchlists fachlich mit Tags und News weiterziehen.
  Erledigt: `watchlist_item_tags`-Tabelle eingefuehrt; Watchlist-API um Tags sowie Krypto-taugliche Item-Update/Delete-Pfade erweitert; aggregierter Endpunkt `/api/watchlists/{id}/news` mit Assetmetadaten, Tags und News-Sentiment gebaut; Backup-Export/-Import um Watchlist-Tags erweitert; API-Regression gegen frisch gebaute Images erfolgreich.
  Offen: die neuen Watchlist-Daten muessen noch im Frontend sichtbar werden; News/Signals sollen spaeter priorisiert und in Alerts/Popups ueberfuehrt werden.

- Datum: 2026-03-20
  Kontext: Das Produktziel wieder an die Roadmap binden und nicht in weiterer Plattformpolitur stecken bleiben.
  Erledigt: erste echte Phase-1-Scheibe umgesetzt; zentrale Assetklassifizierung fuer `stock`/`etf`/`crypto` eingefuehrt; Suche, Scanner und Analyse liefern jetzt normalisierte Assetmetadaten; Suchfallback fuer symbolbasierte Queries ohne Alpaca-Assetcache ergaenzt; API-Regression um Analyse-, Such- und Scanner-Metadaten erweitert und erfolgreich gegen frisch gebaute Images ausgefuehrt.
  Offen: naechste fachliche Schritte sind UI-Nutzung dieser Metadaten, News-Bindung und breitere Live-Datenabdeckung fuer Phase 1.

- Datum: 2026-03-20
  Kontext: Logging- und Auditierbarkeits-Haertung fuer den rekonstruierten Backend-Stand fortsetzen.
  Erledigt: JSON-Logging um Request-Kontext erweitert; HTTP-Middleware schreibt `X-Request-ID`, Methode, Pfad, Client-IP, Status und Laufzeit in strukturierte Logs; Audit-Logs fuer Auth-, Mail- und Push-Pfade redigieren identifizierende Werte jetzt auf IDs/Fingerprints; schlanker Unittest fuer Formatter/Context/Fingerprint wurde ergaenzt.
  Offen: dieselbe Telemetrie-Qualitaet fuer Background-Jobs und WebSockets nachziehen sowie produktive VAPID-Secrets ohne Code-Defaults erzwingen.

- Datum: 2026-03-18
  Kontext: Docker-Hub-Repositories fuer das Trading-Projekt identifizieren und lokal unter `/codex` synchronisieren.
  Erledigt: `dbergt/trading-bot-frontend` und `dbergt/trading-bot-backend` verifiziert, Images auf Aktualitaet geprueft, Projekt unter `/codex/trading-bot-v2` rekonstruiert.
  Offen: Originalen Frontend-Quellstand beschaffen und Publish-Namensschema bereinigen.

- Datum: 2026-03-18
  Kontext: Tiefenanalyse des Tools und Ableitung eines Entwicklungsplans.
  Erledigt: Architektur, API-Flaeche, Auth, Persistenz, Sicherheitslage und Betriebsgrenzen dokumentiert.
  Offen: priorisierte Umsetzung der Security- und Architekturmassnahmen.

- Datum: 2026-03-18
  Kontext: Phase-1-Sicherheitshaertung im Backend.
  Erledigt: JWT ohne unsicheren Fallback erzwungen, CORS auf explizite Origins umgestellt, Alpaca-Secrets verschluesselt gespeichert, Passwort-Reset-Tokens gehasht, Login- und Reset-Rate-Limits eingebaut.
  Offen: produktive Reset-Zustellung, pro-User-Watchlists, strukturierte Logging- und Telemetriehaertung.

- Datum: 2026-03-18
  Kontext: Watchlist-Persistenz von globalem JSON auf pro-User-Datenbankmodell umstellen.
  Erledigt: neue Tabellen fuer Watchlists und Watchlist-Items eingefuehrt, Default-Watchlists pro User seeding-basiert, Watchlist- und Scanner-Endpunkte auf DB-Persistenz umgestellt.
  Offen: automatische Migration alter `watchlists.json`-Inhalte in die neuen Tabellen.

- Datum: 2026-03-18
  Kontext: Produktziel auf vollwertige Trading-Workstation ausweiten.
  Erledigt: Zielbild, Phasenmodell, Datenanbieter-Stack und Plattformanforderungen in `docs/admin/product-roadmap.md` festgehalten.
  Offen: Anbieterwahl finalisieren und mit Phase 0 (Backups, Export/Import, Docker-Hub-Sync) beginnen.

- Datum: 2026-03-18
  Kontext: Plattformfundament fuer Backups, Export/Import und PostgreSQL-Ready-Betrieb.
  Erledigt: `DATABASE_URL`-Abstraktion, PostgreSQL-Service im Compose, Backup-Scheduler, Admin-Endpunkte fuer Export/Import/Backup/Download sowie Backup-Service-Modul umgesetzt.
  Offen: echte Runtime-Pruefung mit installierten Dependencies und dauerhafter Docker-Hub-Multi-Image-Sync.

- Datum: 2026-03-18
  Kontext: Vollstaendige Fortsetzungsfaehigkeit fuer spaetere Sitzungen sicherstellen.
  Erledigt: exakter Handover-Stand in `state/handover-2026-03-18.md` dokumentiert; Wiedereinstieg, offener Punktestand und Prioritaeten festgehalten.
  Offen: naechste Sitzung soll direkt mit Runtime-Validierung und anschliessendem Produktausbau fortsetzen.

- Datum: 2026-03-18
  Kontext: Im dokumentierten Wiedereinstieg die Browser-/UI-Regression als echten CI-/Publish-Gate umsetzen.
  Erledigt: `tests/run-ui-regression.sh` fuehrt den Compose-Stack isoliert aus, wartet auf Health, startet die Browserprobe und schreibt Artefakte; `ci.yml` und `publish.yml` fuehren die UI-Regression nun inklusive Artefakt-Upload aus.
  Offen: GitHub-Lauf mit echten Runnern beobachten und die UI-Probe spaeter um weitere Kernfluesse erweitern.

- Datum: 2026-03-18
  Kontext: Den Multi-Image-Docker-Hub-Sync lokal technisch absichern, ohne sofort einen echten Push auszufuehren.
  Erledigt: `ops/automation/sync-components.sh` unterstuetzt jetzt `DRY_RUN=1` und `SKIP_BUILD=1` fuer einen lokalen Publish-Vorabtest mit vorhandenen Images.
  Offen: echten Push gegen Docker Hub mit realen Secrets einmal kontrolliert ausfuehren.

- Datum: 2026-03-18
  Kontext: Den GitHub-Publish-Workflow fuer einen sicheren Vorabtest vorbereiten.
  Erledigt: `publish.yml` unterstuetzt jetzt `workflow_dispatch` mit `dry_run=true`, ueberspringt dann Docker-Login/Push und nutzt vorhandene lokale Images statt doppelt zu bauen.
  Offen: Dry-Run in GitHub Actions einmal ausfuehren und anschliessend einen echten Publish-Lauf pruefen.

- Datum: 2026-03-18
  Kontext: Den offenen Produktpunkt fuer produktive Passwort-Reset-Zustellung abschliessen.
  Erledigt: Passwort-Reset verschickt nun SMTP-Mails an einen konfigurierbaren Frontend-Link; `.env.example` dokumentiert `PASSWORD_RESET_BASE_URL` und `SMTP_*`; die API-Regression prueft jetzt auch Reset-Request, Confirm und Re-Login.
  Offen: SMTP-Konfiguration einmal mit echter Mail-Infrastruktur pruefen und Logging spaeter weiter strukturieren.

- Datum: 2026-03-18
  Kontext: Die neue Passwort-Reset-Mailzustellung nicht nur im Code, sondern auch zur Laufzeit verifizieren.
  Erledigt: `tests/run-password-reset-email-smoke.sh` startet einen lokalen SMTP-Capture-Server im Docker-Testnetz und prueft Reset-Mail, Link-Extraktion, Confirm und Re-Login erfolgreich end to end.
  Offen: denselben Pfad spaeter gegen einen echten externen SMTP-/Mail-Provider pruefen.

- Datum: 2026-03-18
  Kontext: Den vorbereiteten Multi-Image-Docker-Hub-Publish jetzt real ausfuehren.
  Erledigt: `SKIP_BUILD=1 bash ops/automation/sync-components.sh` hat beide Images erfolgreich nach Docker Hub gepusht:
  `dbergt/trading-bot-backend:latest` -> `sha256:6ccd0f476169e184d30c80b7dacdb8f99b6fee65e92f98c8c7a722205052bf84`,
  `dbergt/trading-bot-frontend:latest` -> `sha256:201169e45e11e6edc2fade078cda4d93dfff509dd65d6a42394b7def31fe7167`.
  Offen: denselben Pfad noch einmal kontrolliert in GitHub Actions mit den echten Secrets ausfuehren und die Governance-Frage des Zwei-Image-Modells finalisieren.

- Datum: 2026-03-18
  Kontext: Den lokalen Fortsetzungsstand nach dem Docker-Hub-Publish erneut runtime-validieren.
  Erledigt: aktueller Quellstand neu gebaut; `tests/run-api-regression.sh` repariert, weil der Export-Test nach bewusst angelegtem Zusatznutzer faelschlich weiter `1` Benutzer erwartete; API-Regression und UI-Regression danach erneut erfolgreich ausgefuehrt.
  Offen: ein echter getaggter Docker-Hub-Release plus `deploy.sh`-basiertes Upgrade-Rehearsal bleibt der naechste externe Validierungsschritt; lokal ist der aktuelle Stand wieder gruen.

- Datum: 2026-03-18
  Kontext: Verlustfreien Docker-Hub-Only-Deploy- und Upgrade-Pfad festziehen.
  Erledigt: Compose auf parametrisierte Docker-Hub-Image-Refs umgestellt; persistente Runtime-Daten aus dem Quellbaum nach `state/runtime/...` verlagert; `ops/automation/deploy.sh` fuer Deploy/Upgrade mit Pre-Upgrade-Backup, automatischem Rollback-Versuch und Deployment-Record umgesetzt; Release- und Betriebsdoku auf Docker-Hub-only ausgerichtet.
  Offen: den Pfad jetzt mit einem explizit getaggten Release und einem echten Upgrade-Fall gegen vorhandene Daten proben.

- Datum: 2026-03-18
  Kontext: Den neuen Docker-Hub-Release- und Deploy-Pfad technisch verifizieren.
  Erledigt: `SKIP_BUILD=1 DRY_RUN=1 IMAGE_TAG=2026.03.18-testdeploy bash ops/automation/sync-components.sh` lief erfolgreich und schrieb `state/releases/2026.03.18-testdeploy.env`; isolierter Docker-Hub-Deploy-Smoke-Test via `ops/automation/deploy.sh` auf temporaeren Runtime-Pfaden und eigenen Ports lief ebenfalls erfolgreich und schrieb `state/runtime/deployments/deployment-20260318T211121Z.env`.
  Offen: naechster echter Betriebscheck ist nun ein Upgrade ueber bereits vorhandene Daten inklusive Pre-Upgrade-Dump und Restore-Test.

- Datum: 2026-03-18
  Kontext: Den naechsten Betriebscheck als vollstaendiges Upgrade-/Restore-Rehearsal gegen einen echten Docker-Hub-Release fahren.
  Erledigt: explizite Releases `2026.03.18-1` und danach der Fix-Release `2026.03.18-2` wurden nach Docker Hub gepusht; `tests/run-upgrade-rehearsal.sh` wurde fuer initialen Deploy, Datenanlage, Upgrade ueber bestehenden Datenbestand, Pre-Upgrade-Dump, App-Snapshot und Dump-Restore gebaut; der Restore-Blocker im Legacy-Watchlist-Migrationspfad wurde behoben; das vollstaendige Rehearsal lief fuer `2026.03.18-2` erfolgreich durch.
  Offen: denselben Rehearsal-Pfad kuenftig fuer jeden neuen Release-Tag erneut fahren; Frontend-Quellstand und weitere Produktarbeit bleiben offen.
