<!-- page: /alerts -->
# Alerts

Alerts are persistent rules that fire alert events when the underlying signal crosses a threshold. Events show up on the dashboard alert panel, can be pushed via Web Push to subscribed browsers, and stay in the audit history until you acknowledge them.

## Rule types

- **provider_move** — fires when the symbol's intraday move crosses the threshold (in percent). Useful for "ping me when AAPL moves more than 2% today".
- **news_sentiment** — fires when the aggregated VADER sentiment for the symbol's news drops below or rises above a threshold.
- **signal_direction** — fires when the ML prediction switches direction (UP → DOWN or DOWN → UP).
- **tag_priority** — fires when any tagged item in the watchlist hits a priority level. Used for "anything tagged 'core' should ping me on high-priority alerts".

## Per-watchlist settings

Each watchlist has its own alert configuration: enabled / disabled, popup vs push, minimum priority and minimum score. Configure them on the dashboard's Alert Management panel; they cascade to every alert rule scoped to the watchlist.

## Snoozing

Each rule can be snoozed until a specific time. The dispatcher skips snoozed rules entirely until the snooze expires.
