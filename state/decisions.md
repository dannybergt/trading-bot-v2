# Entscheidungen

- Datum: 2026-05-05
  Entscheidung: `docs/admin/project-plan.md` ist ab jetzt die kanonische Kurzverankerung fuer Gesamtstand, Phasenposition, Sicherheitsachsen und naechste Prioritaeten.
  Begruendung: Nach `v2026.05.05-1` ist das Projekt nicht mehr nur ein rekonstruiertes MVP, sondern ein releasefaehiger Phase-1-Stand mit begonnener Research-Schicht und aktivem Alert-Dispatcher. Der Gesamtplan muss deshalb explizit sichtbar bleiben, damit einzelne Folgeaufgaben nicht vom Produkt-, Betriebs- oder Sicherheitsziel abweichen.
  Konsequenzen: Roadmap, README, Release- und Security-Doku verweisen auf den aktuellen validierten Release und die naechsten Guardrails; neue groessere Arbeiten muessen gegen Phasenplan, Security, Tests, Backup/Export/Import und Rehearsal-Regeln eingeordnet werden.

- Datum: 2026-04-26
  Entscheidung: Dauerhafte private lokale Secrets und persoenliche Zugangsdaten werden in einer gitignorierten `.env.local` gepflegt, die von den Ops-Skripten immer nach `.env` geladen wird.
  Begruendung: Der bisherige Betriebsweg war fehleranfaellig, weil `docker compose -f ops/docker/compose.yaml ...` die Root-`.env` nicht verlaesslich als Projektkontext behandelt und Nutzer dadurch Keys bei Wiedereinstiegen wiederholt neu eintragen mussten.
  Konsequenzen: `start.sh`, `stop.sh` und `logs.sh` kapseln den Compose-Zugriff; `.env` bleibt Basis-Konfiguration, `.env.local` gewinnt fuer private Overrides; Deploy- und Rehearsal-Skripte verwenden denselben Ladepfad.

- Datum: 2026-03-18
  Entscheidung: Lokalen Projektordner als `trading-bot-v2` angelegt.
  Begruendung: Dieser Name ist in beiden Images als Compose-/Projektname verankert und beschreibt das Gesamtprodukt besser als die getrennten Image-Namen.
  Konsequenzen: Publish-Automation braucht eine gesonderte Namensentscheidung.

- Datum: 2026-03-18
  Entscheidung: Backend-Quellcode aus Image extrahiert und als Arbeitsbasis uebernommen.
  Begruendung: Docker Hub war die einzig verifizierbare Quelle. Damit ist wenigstens der serverseitige Stand nachvollziehbar bearbeitbar.
  Konsequenzen: Der lokale Stand ist editierbar, aber nicht automatisch identisch mit einem moeglichen privaten Git-Repository.

- Datum: 2026-03-18
  Entscheidung: Frontend nur als `frontend-dist` abgelegt.
  Begruendung: Im Image war kein Quellstand vorhanden, nur das ausgelieferte Bundle.
  Konsequenzen: Tiefere Frontend-Weiterentwicklung ist ohne weitere Rekonstruktion oder Originalquelle eingeschraenkt.

- Datum: 2026-03-18
  Entscheidung: Publish-Automation nicht auf Docker Hub freigeschaltet.
  Begruendung: Die globale Regel verlangt exakte Namensgleichheit zwischen Projektordner und Image-Repository; diese ist aktuell nicht gegeben.
  Konsequenzen: Build und Analyse sind moeglich, Publish erst nach Strukturentscheidung.

- Datum: 2026-03-18
  Entscheidung: Backend-Container bleibt als nicht-root User laufend; beschreibbare Bind-Mount-Pfade werden ueber Automation vorbereitet.
  Begruendung: Die Runtime-Pruefung zeigte Schreibprobleme fuer `state/runtime/backups`, aber ein Root-Container waere der falsche Sicherheitsrueckschritt.
  Konsequenzen: `ops/automation/build.sh` erzeugt und chmodet die benoetigten Runtime-Verzeichnisse vor dem Compose-Start.

- Datum: 2026-03-18
  Entscheidung: Backup-Scheduler faengt Laufzeitfehler ab und beendet sich nicht dauerhaft beim ersten Fehler.
  Begruendung: Ein einzelner Schreib- oder IO-Fehler darf die gesamte geplante Backup-Funktion nicht stilllegen.
  Konsequenzen: Scheduler-Fehler landen im Log, der Task laeuft danach weiter.

- Datum: 2026-03-18
  Entscheidung: Frontend-Zugriffe laufen ueber Nginx mit SPA-Fallback sowie Proxy fuer `/api` und `/ws`.
  Begruendung: Das ausgelieferte Frontend-Bundle verwendet relative `/api/...`-Aufrufe und clientseitige Routen wie `/login`; ohne Proxy und `try_files` war der Compose-Gesamtlauf funktional unvollstaendig.
  Konsequenzen: `ops/docker/frontend.nginx.conf` ist nun Teil des produktiven Frontend-Images und muss bei Frontend-Anpassungen mitgedacht werden.

- Datum: 2026-03-18
  Entscheidung: Distribution und Deployments werden operativ ausschliesslich ueber Docker Hub gefahren; GitHub ist kein benoetigter Betriebsbaustein.
  Begruendung: Nutzerseitige Vorgabe ist Docker Hub als einzige Ablage und als Distribution Point.
  Konsequenzen: Release- und Upgrade-Prozeduren muessen lokal per Shell/Compose reproduzierbar sein; Doku und naechste Schritte duerfen keinen GitHub-Pflichtpfad mehr voraussetzen.

- Datum: 2026-03-18
  Entscheidung: Persistente Runtime-Daten werden standardmaessig unter `state/runtime/...` gehalten, nicht im Quellbaum.
  Begruendung: Code und laufende Daten muessen fuer verlustfreie Upgrades und saubere Docker-Hub-Deployments getrennt sein.
  Konsequenzen: Compose und Build-Automation verwenden jetzt `state/runtime/backend-data`, `state/runtime/backups` und `state/runtime/postgres`.

- Datum: 2026-03-18
  Entscheidung: Der Legacy-Watchlist-Migrationspfad darf bei nicht-SQLite-Datenbanken nicht mehr ausgefuehrt werden.
  Begruendung: Ein PostgreSQL-basierter Deploy oder Dump-Restore darf nicht an einem alten SQLite-Sidepath scheitern.
  Konsequenzen: `migrate_watchlists.py` ueberspringt den SQLite-Migrationspfad nun sauber bei nicht-SQLite-`DATABASE_URL` oder fehlender SQLite-Datei.

- Datum: 2026-03-20
  Entscheidung: Assetklassifizierung fuer Phase 1 wird zentral aus Provider-Metadaten mit heuristischen Symbol-Fallbacks abgeleitet.
  Begruendung: Suche, Scanner und Analyse brauchen sofort nutzbare Assetmetadaten, obwohl Providerzugriff und Frontend-Quellstand aktuell nicht in jedem Pfad vollstaendig verfuegbar sind.
  Konsequenzen: `asset_metadata.py` liefert die gemeinsame Klassifizierungslogik fuer `stock`, `etf` und `crypto`; API-Responses nutzen einheitliche Felder und koennen auch ohne Alpaca-Assetcache fuer symbolbasierte Requests sinnvoll antworten.

- Datum: 2026-03-20
  Entscheidung: Watchlist-Tags werden als eigene relationale Tabelle statt als Freitextfeld oder JSON-Spalte modelliert.
  Begruendung: Tags sollen spaeter fuer Filter, Alerts, News-Bindung und potenzielle UI-Gruppierung wiederverwendbar sein und muessen sauber exportierbar bleiben.
  Konsequenzen: `watchlist_item_tags` wird bei `init_db()` automatisch angelegt; Watchlist-Export/-Import und API-Responses tragen Tags nun explizit; Krypto-Symbole muessen in Watchlist-Item-Routen als `path`-Parameter behandelt werden.

- Datum: 2026-03-20
  Entscheidung: Watchlist-Alerts werden vorerst backend-seitig aus technischer Signalstaerke, News-Sentiment, News-Frische und Watchlist-Tags priorisiert.
  Begruendung: Der Frontend-Quellstand fehlt noch, aber Phase 1 braucht bereits eine nutzbare Alert-/Popup-Basis statt nur ungeordneter News-Listen.
  Konsequenzen: `/api/watchlists/{id}/alerts` liefert jetzt priorisierte Alert-Kandidaten; die Priorisierungslogik liegt isoliert in `watchlist_alerts.py` und ist host-seitig unit-getestet, kann spaeter aber mit produktiveren Providerdaten und UI-Feedback weiter kalibriert werden.

- Datum: 2026-03-20
  Entscheidung: Der Trading-Bot bekommt einen Bootstrap-Superadmin per Umgebungsvariablen statt eines hartcodierten Default-Kontos.
  Begruendung: Es braucht einen sicheren Erstzugang fuer Benutzerverwaltung und Admin-Endpunkte, aber globale Regeln verbieten Demo-Secrets oder fest eingebaute Standardpasswoerter.
  Konsequenzen: `INITIAL_ADMIN_EMAIL` und `INITIAL_ADMIN_PASSWORD` muessen fuer den Erstaufbau gesetzt werden; bei `INITIAL_ADMIN_MFA_ENABLED=false` ist der erste Login ohne OTP moeglich; der Seed-Pfad greift nur, wenn noch kein Admin existiert.

- Datum: 2026-03-23
  Entscheidung: Pushes nach `main` publizieren Docker-Hub-Images automatisch sowohl als `latest` als auch als unveraenderlichen `sha-<commit>`-Tag; Git-Tags `v*` publizieren weiterhin versionierte Release-Tags.
  Begruendung: Der Nutzer will die Git- und Registry-Synchronisierung ohne manuellen Nachlauf. Gleichzeitig muss der produktive Deploy-Pfad weiter an explizit nachvollziehbare Release-Tags gebunden bleiben.
  Konsequenzen: GitHub Actions wird zum kontinuierlichen Sync-Pfad fuer Integrationsstaende; `latest` ist nur ein beweglicher Integrationszeiger, produktive Upgrades bleiben bei expliziten Versionstags; fuer den Automatikpfad muessen funktionierende Docker-Hub-Secrets im Repository hinterlegt bleiben.
