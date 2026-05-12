<!-- page: /alerts -->
# Alerts

Alerts sind persistente Regeln, die Alert-Events ausloesen, wenn das zugrundeliegende Signal eine Schwelle ueberschreitet. Events erscheinen im Alert-Panel des Dashboards, koennen per Web Push an abonnierte Browser gepusht werden und bleiben im Audit-Verlauf, bis sie quittiert werden.

## Regeltypen

- **provider_move** — feuert, wenn die Intraday-Bewegung des Symbols die Schwelle (in Prozent) ueberschreitet. Nuetzlich fuer "ping mich, wenn AAPL heute mehr als 2 Prozent bewegt".
- **news_sentiment** — feuert, wenn der aggregierte VADER-Sentiment-Score der News zum Symbol eine Schwelle unter- oder ueberschreitet.
- **signal_direction** — feuert, wenn die ML-Prediction die Richtung wechselt (UP → DOWN oder DOWN → UP).
- **tag_priority** — feuert, wenn ein getaggter Eintrag in der Watchlist eine Prioritaetsstufe erreicht. Genutzt fuer "alles mit Tag 'core' soll mich bei hochprioren Alerts pingen".

## Per-Watchlist-Settings

Jede Watchlist hat ihre eigene Alert-Konfiguration: aktiviert/deaktiviert, Popup vs Push, Mindestprioritaet und Mindestscore. Konfiguration im Alert-Management-Panel des Dashboards; die Settings kaskadieren auf jede Alert-Regel im Scope der Watchlist.

## Snoozing

Jede Regel kann bis zu einem konkreten Zeitpunkt geschnoozed werden. Der Dispatcher ueberspringt geschnoozede Regeln vollstaendig, bis der Snooze abgelaufen ist.
