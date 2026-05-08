<!-- page: /docs -->
# Getting started

This is the in-app documentation root. Pick a topic from the sidebar, or use the contextual help drawer (the **?** button in the header) on any page to get a short summary plus a link back here.

## Recommended reading order

1. **[Dashboard](/docs/dashboard)** — what you'll see after sign-in and how the surfaces relate.
2. **[Watchlists](/docs/watchlists)** — the symbol universe that drives every other view.
3. **[Symbol analysis](/docs/analysis)** — every signal we pull for a single ticker.
4. **[Paper trading](/docs/paper-trading)** — placing simulated orders, the Net-Yield-Gate, and the trade journal.
5. **[Alerts](/docs/alerts)** — persistent rules and how they fire.
6. **[Settings](/docs/settings)** — broker keys, fees, taxes, MFA.
7. **[Administration](/docs/admin)** — only relevant if your role is admin.

## How recommendations work

Every per-symbol recommendation combines five signal classes — Fundamentals, News, Trend, Technical, AI — into a probability-weighted prediction. The model only flags a buy/sell as "actionable" when the projected NET return after broker fees and capital-gains tax clears your `min_target_yield` threshold (set under [Settings](/settings)).

## Privacy

Identifying values (email addresses, IPs, user agents) in the audit log are stored as one-way SHA-256 fingerprints. Broker secrets are encrypted at rest. Backups carry the fingerprints, never plaintext PII.
