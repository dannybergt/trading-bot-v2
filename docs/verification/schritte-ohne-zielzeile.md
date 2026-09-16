# Harnisch-Schritte, die keine Zielzeile bewachen

Gegenstueck zu `zielkatalog.md`. Der Katalog fragt: *ist jedes Versprechen
belegt?* Diese Datei fragt die Gegenrichtung: *bewacht jeder Pruefschritt ein
Versprechen?*

**Warum das zaehlt.** Der Katalog haelt seit dem 2026-08-05 die Notiz "43 von 75
Harnisch-Schritten bewachen keine Zielzeile". Die Zahl stand als Fliesstext da
und ist seitdem still auf **72 von 87** gewachsen — jeder neue Schritt erhoehte
sie, ohne dass irgendetwas rot wurde. Genau das ist das Muster, das diesem
Projekt in dieser Woche mehrfach begegnet ist: eine Aussage ueber den eigenen
Pruefstand, die niemand nachrechnet.

Ab jetzt rechnet `tests/test_harness_step_coverage.py` sie nach. Jeder Schritt
der beiden Regressionen muss entweder im Zielkatalog als Beweisschritt genannt
sein **oder** hier stehen. Ein neuer Schritt, der weder das eine noch das
andere ist, macht den Guard rot.

**Stand: 75 von 90 Schritten stehen hier.** Diese Zeile ist keine Notiz — der
Guard liest beide Zahlen und faellt, sobald sie nicht mehr stimmen. Die
Abschnitte darunter tragen bewusst **keine** Einzelzahlen: sie wuerden genauso
verrotten wie die Zahl, die diese Datei ersetzt.

**Was hier zu stehen bedeutet.** Kein Makel. Ein Vertragsschritt bewacht die
Grundlage, auf der die Zielzeilen ueberhaupt messbar sind — dass Anlegen und
Loeschen konsistent bleiben, dass eine Antwort ihre Form haelt, dass eine Seite
laedt. Was er **nicht** tut: ein Produktversprechen belegen. Diese Trennung
sichtbar zu halten ist der Zweck der Datei.

**Eigentum.** Wie im Katalog: der Mensch besitzt die Zielsaetze. Die Vorschlaege
unten sind Vorschlaege — der Agent traegt sie hier ein, in den Katalog kommen
sie erst nach einer Entscheidung.

## Vertragsschritte

### Watchlisten

`watchlist create` · `watchlist create does not reseed defaults` ·
`watchlist add tagged item` · `watchlist add etf item` ·
`watchlist update tagged item` · `watchlist list tags` · `watchlist news binding` ·
`watchlist delete incl default` · `watchlist crypto delete` · `watchlist etf delete` ·
`watchlist alert settings` · `ui_watchlists`

Rundlauf und Schema der Watchlist-Bearbeitung. `watchlist create does not reseed
defaults` bewacht einen konkreten Vorfall (Seeding aus dem Lesepfad liess
geloeschte Startlisten wieder auferstehen) — ein Regressionsschutz, kein
Versprechen.

### Alarmregeln

`alert rule create` · `alert rule list` · `alert rule price target create` ·
`alert rule update and disable` · `alert rule rejects unknown type` ·
`alert evaluation event` · `alert event ack` · `alert event list` ·
`acknowledged alert event list`

Siehe **V1** — hier fehlt eine Zielzeile, nicht ein Schritt.

### Paper Trading

`paper trading settings` · `paper trading order placed` · `paper trading cancel` ·
`paper trading orders list` · `paper trading positions list` ·
`paper trading transactions list` · `paper trading summary`

Das Produktversprechen dahinter ist das Net-Yield-Gate (TBV2-Z03) und hat eigene
Schritte in beiden Richtungen. Diese hier sichern die Umgebung, in der das Gate
ueberhaupt greifen kann.

### Auto-Execution (5)

`auto-execution limits read` · `auto-execution limits update` ·
`auto-execution limits reject double-encoded body` · `auto-execution halt` ·
`auto-execution halt disables master switch`

Siehe **V2**. Der Schritt fuer den doppelt kodierten Rumpf bewacht einen
konkreten Fehlerfall der Eingabepruefung.

### Sicherung und Import

`manual backup` · `backup list` · `backup download` · `backup import` ·
`platform import` · `export`

TBV2-Z10 deckt Upgrade und Restore ueber den **pg_dump**-Pfad ab. Diese Schritte
bewachen den **App-Import** daneben — dort sass die Fremdschluesselverletzung vom
2026-08-05. `export` prueft, dass der Schnappschuss die Tabellen mit ihren
Werten wirklich enthaelt; er ist der Grund, warum eine neue Spalte nicht still
aus der Sicherung fallen kann.

### Konten und Zugang

`bootstrap admin login` · `bootstrap admin profile` · `admin create user` ·
`admin password reset` · `member login after admin reset` ·
`password reset request` · `password reset confirm` · `login after reset` ·
`ui_login_screen` · `ui_register_screen`

Sicherheitsverhalten. TBV2-Z11 deckt die serverseitige Absicherung geschuetzter
Funktionen ab, nicht diese Ablaeufe.

### Stammdaten und Recherche

`stock asset metadata` · `crypto asset metadata` · `search asset metadata` ·
`scanner asset metadata` · `research signals + macro context + social sentiment shape` ·
`crypto research + crypto metrics shape` · `crypto research context` ·
`etf research context` · `symbol events provider status names its cause`

Diese Schritte pruefen die **Form** der Antworten, nicht die Richtigkeit der
Werte. `symbol events provider status names its cause` ist die Ausnahme: er
verlangt, dass ein Anbieterausfall seine Ursache nennt — inhaltlich nahe an
TBV2-Z06 (b), aber ohne dass der Katalog ihn fuehrt.

### Betrieb

`health` · `push config unavailable`

### Oberflaechen-Geruest (8)

`ui_dashboard` · `ui_scanner` · `ui_analysis` · `ui_alerts` · `ui_settings` ·
`ui_paper_trading` · `ui_admin` · `ui_pwa_manifest`

Die Seite laedt, ihre Kernelemente sind da, ein angemeldeter Nutzer kommt hin.
Notwendig, damit die zielbewachenden Schritte ueberhaupt etwas vorfinden — fuer
sich genommen aber kein Produktversprechen. `ui_analysis` prueft heute nur, dass
ein Chart-Element rendert; die inhaltlichen Zusagen der Analyse-Seite haengen an
Z02 und Z06 mit eigenen Schritten.

### Paper-Trading-Formular (1)

`ui_paper_order_no_price`

Eine Market-Order fuer ein Symbol, fuer das kein Anbieter einen Kurs liefert,
wird an der Grenze abgewiesen, und die Seite nennt das getippte Symbol statt des
Allgemeinsatzes. Gefunden 2026-09-16: eine "AMAZON"-Order stand auf der
deployten Instanz 21 h still auf pending; danach zeigte die Seite trotz
400-mit-Grund nur "Order could not be placed." — `ApiError.detail` trug die
ganze Antwort, `detail.reason` griff ins Leere, und dasselbe galt seit dem
Scaffold fuer die Net-Yield-Ablehnung (Z03/Z06 (d) haben bis heute keinen
UI-Beweisschritt fuer dieses Formular). Gegenstand von **V7**.

### Backtest (2)

`backtest never blocks the request path` · `ui_backtest_pending`

Seit dem 2026-09-15 rechnet der Backtest im Hintergrund; der Endpunkt antwortet
sofort mit `ready`, `pending` oder `failed`, die Karte holt das Ergebnis nach.
Trennschaerfe, ehrlich je Umgebung: `backtest never blocks the request path`
beweist ohne Providerzugang nur, dass der synthetische Pfad sofort und ohne
Job `ready` + leer antwortet (Regel K) und dass ohne Token 401 kommt; erst mit
echten Bars verlangt er `pending` beim ersten Aufruf und einen Poll unter einer
Sekunde. Der Modus steht in der Ausgabe. `ui_backtest_pending` beantwortet
`/api/backtest/*` auf CDP-Ebene selbst (erst `pending`, dann `ready`), weil der
synthetische Host den Zweig sonst nie zeigt — bewiesen sind damit die
Pending-Karte, das Nachholen ohne Reload, der Datenstand am Herkunftshinweis
und dass der Poll danach **endet**; nicht bewiesen ist, dass das Backend selbst
diese Folge liefert (das tun die Unit-Tests und der `verifier`). Gegenstand von
**V5**.

### Warten auf eine Zielzeile

`ui_auto_execution_limits_persist` · `ui_symbol_search` · `ui_token_persisted`

Gegenstand von **V2**, **V3** und **V4**. Sie stehen hier, weil sie heute keine
Zielzeile bewachen — nicht, weil sie keine verdienen.

Der Schritt ui_admin_i18n_german stand hier bis zum 2026-08-11 und ist jetzt bei
**TBV2-Z08** eingetragen: er belegt, dass die Admin-Seite uebersetzt bleibt, und
das ist genau die Zusage dieser Zeile. Sein Name steht hier absichtlich ohne
Codezeichen — sonst zaehlte ihn der Guard weiterhin zu dieser Liste.

## Vorschlaege an den Menschen

Neue Zielsaetze schreibt der Agent nicht. Diese fuenf sind vorbereitet und warten
auf eine Entscheidung.

### V1 — Der Alarm-Feed hat kein Versprechen

Betrifft: `watchlist alerts priority feed`, `alert evaluation event`,
`alert event ack`, `alert event list`, `acknowledged alert event list`, `ui_alerts`

Watchlist-Alarme mit Prioritaet, Popup und Push sind ein Kernstueck des Produkts.
**Sechs** Schritte bewachen sie, und gemessen wird gegen nichts. Vorschlag fuer
den Zielsatz: *ein Alarm erreicht den Nutzer genau dann, wenn er die von ihm
gesetzte Schwelle ueberschreitet — und er sagt, worauf er beruht.* Der zweite
Halbsatz ist seit dem 2026-08-11 belegbar: der Feed weist ausgelassene Symbole
als `degraded` aus.

### V2 — Der Not-Aus der Automatik

Betrifft: `auto-execution halt`, `auto-execution halt disables master switch`,
`ui_auto_execution_limits_persist`

Dass der Not-Aus greift **und** den Hauptschalter mitnimmt, wird geprueft — aber
nicht gegen einen formulierten Zielsatz. Bei einer Funktion, die echtes Geld
bewegen soll, ist das die Zeile, die am wenigsten fehlen darf.

### V3 — Was bei Ablauf der Sitzung passiert

Betrifft: `ui_token_persisted`

Am 2026-08-05 machte eine **abgelaufene** Sitzung die Anwendung unbenutzbar, und
keine Pruefung hat es gefunden — jede war schneller als die Sitzungsdauer.
`ui_token_persisted` prueft heute nur, dass ein Token einen Reload ueberlebt.
Vorschlag: *eine abgelaufene Sitzung fuehrt zurueck zur Anmeldung, nicht in eine
unbenutzbare Oberflaeche* — mit einem Schritt, der den Ablauf **herstellt**
(Token verfaelschen oder Ablaufzeit vorziehen), statt auf ihn zu warten.

### V4 — Die Symbolsuche

Betrifft: `ui_symbol_search`

Einstieg in jede Analyse, im STATE als dauerhaft unbewiesen gefuehrt (Stufe 3,
braucht Providerzugang). Eine Zielzeile wuerde diese Luecke im Katalog sichtbar
machen, statt sie in einer Notiz zu fuehren.

### V7 — Eine Order ohne Kurs wird mit dem getippten Symbol abgewiesen

Betrifft: `ui_paper_order_no_price`; dazu der api-regression-Schritt fehlt noch
(Market-Order ohne Kurs -> 400 `no_price_for_symbol`, Audit `paper_order.place_rejected`).

Vorschlag fuer den Zielsatz: "Eine Order, fuer die kein Anbieter einen Kurs
liefert, wird an der Grenze abgewiesen — API 400 mit Grund und Symbol, Audit-
Zeile, Satz in der Oberflaeche (DE/EN) — statt still pending zu bleiben."
Beobachtbares Kriterium: Market-Order fuer ein Nicht-Symbol -> 400 + Satz mit dem
Symbol, keine Order in der Liste; Limit-Order ohne Kurs -> pending (sie traegt
ihren Preis selbst). Dazu gehoert als Kriterium zu Z07: der juengste Kursbalken
ist hoechstens 7 Kalendertage alt, sonst sagt das Badge `stale` (V6, ADR
2026-09-16 zweiter Eintrag) — beweisbar nur mit Anbieter (Stufe 3).

### V5 — Der Backtest rechnet nie auf Platzhalterkursen und nie im Anfragepfad

Betrifft: `backtest never blocks the request path`, `ui_backtest_pending`

Vorschlag fuer den Zielsatz: "Die Modellguete auf `/analysis/<symbol>` stammt
aus einem Walk-Forward auf echten Kursen; die Seite wartet nie auf die
Rechnung, zeigt waehrenddessen, dass gerechnet wird, und fuellt sich von
selbst." Beobachtbares Kriterium: `/api/backtest/<symbol>` antwortet durch
nginx mit 200 (`ready`/`pending`/`failed`) in der Zeit, die der Kursabruf beim
Anbieter kostet, und rechnet dabei nichts; ein Poll **bei offenem Job** unter
einer Sekunde (nach `ready` zahlt ein Aufruf den Kursabruf erneut — das ist
kein Poll mehr); auf Platzhalterkursen `ready` mit null Samples und
`synthetic: true`. Die Zeitangaben gelten bei Host-Load unter der Kernzahl —
darueber hungert der Prozess am eigenen Job (`n_jobs=-1`) und am Retrain, und
die Sekunde reisst (verifier 2026-09-16: 1 von 55 Polls bei Load 7–14, 15 von
74 bei Load 16–33). Hintergrund: der Endpunkt war vom ersten Tag an strukturell
leer (kein Zeitraum lieferte genug Bars), danach vier Verifier-Laeufe lang zu
langsam fuer den Proxy (STATE 2026-09-11), und zuletzt rechnete er im
Anfragepfad die Bildschirm-Vorhersage, die die Antwort gar nicht traegt
(2026-09-16) — nichts davon war rot, weil keine Zielzeile es verlangte.
