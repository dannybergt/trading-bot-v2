<!-- page: /docs/data-quality -->
# Data quality and provider transparency

Buy/sell recommendations are only as good as the data feeding them. The platform makes the data foundation visible so you can decide how much weight to put on a recommendation.

## Per-symbol data-quality section

On every `/analysis/<symbol>` page, the Data quality section sits at the top with two pieces of information:

- **Overall confidence** — `high` / `medium` / `low`. High means the majority of the data fields came back full from their primary providers; medium tolerates partial fallbacks; low means most fields are missing or only on heuristic fallbacks.
- **Per-field grid** — each data type (price history, fundamentals, research depth, insider/institutional, earnings calls, options flow, macro context, …) shown with its current confidence and the actual provider that answered. The same overall label is mirrored as a small badge under the ML signal so the recommendation card always sits next to its data foundation.

When something is missing or partial, the section spells out **why**: e.g. "earnings calls — missing — FMP unconfigured" or "options flow — partial — yfinance throttled".

## Upgrade hints

If a configured-but-paid provider would unlock missing data for the symbol you are looking at, an Upgrade hint block lists the recommended tier with cost and concrete benefit. Examples:

- **FMP Starter ($14/month)** — when FMP is unconfigured: unlocks fundamentals depth, insider/institutional signals, and earnings-call digest in one tier.
- **Alpha Vantage Premium ($50/month)** — only relevant when crypto live quotes need higher throughput than the free tier provides.
- **Polygon.io Stocks ($29/month)** — only relevant when options-flow accuracy actually drives decisions.

These are **explicit static rules** and not opaque heuristics — you can audit the rule set in `app/data_quality_service.py::_build_upgrade_hints`.

## Admin data-source coverage matrix

Under [Admin](/admin) → Data sources, the full provider catalogue is rendered as a table: every provider, what it covers, the free-tier limit, the recommended upgrade tier, the monthly cost, and one line on why the upgrade is worth it. The footer shows the additional monthly cost if every recommended upgrade for currently-configured providers were activated.

## Confidence math

The overall label reduces the per-field labels:

- `high`: ≥60% of fields are `full`
- `medium`: ≥60% of fields are `full` + `partial` combined
- `low`: anything else

That ratio is intentionally conservative: when fewer than 60% of the fields come back full, the recommendation should be read with a "smaller position size" mindset.

## Where the rules live

- Rules: `src/backend/app/data_quality_service.py` (per-field confidence, upgrade hints, provider catalogue)
- Endpoints: `GET /api/research/{symbol}/data-quality`, `GET /api/admin/data-sources`
- UI: `DataQualitySection` on `/analysis/<symbol>`, `DataSourcesSection` on `/admin`
