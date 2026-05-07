/**
 * Pure-SVG horizontal volume-by-price histogram.
 *
 * Pairs with `StockChart` but is intentionally not coupled to the
 * lightweight-charts price-scale; it shows the same price range alongside the
 * chart so the eye can correlate volume nodes with the candlestick body.
 */

export type VolumeProfileBin = {
  priceLow: number;
  priceHigh: number;
  volume: number;
};

export type VolumeProfilePayload = {
  bins: VolumeProfileBin[];
  minPrice: number | null;
  maxPrice: number | null;
  totalVolume: number;
  pointOfControl: number | null;
  pointOfControlVolume: number;
};

export function VolumeProfile({ profile }: { profile: VolumeProfilePayload | null | undefined }) {
  if (!profile || profile.bins.length === 0) return null;

  const maxBinVolume = profile.bins.reduce(
    (acc, bin) => Math.max(acc, bin.volume),
    0,
  );
  if (maxBinVolume <= 0) return null;

  // Render bins top-to-bottom from highest price to lowest, matching how a
  // candle chart's price scale reads (high at top).
  const ordered = [...profile.bins].sort((a, b) => b.priceLow - a.priceLow);

  const width = 220;
  const height = 360;
  const barRowHeight = height / ordered.length;
  const labelStripWidth = 60;
  const barAreaWidth = width - labelStripWidth - 4;

  const poc = profile.pointOfControl;

  return (
    <section className="card flex flex-col">
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Volume profile
        </h2>
        {poc != null ? (
          <span className="text-xs text-bergt-green">
            POC {poc.toFixed(2)}
          </span>
        ) : null}
      </header>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="mt-2 h-[360px] w-full"
        role="img"
        aria-label="Volume by price histogram"
      >
        {ordered.map((bin, idx) => {
          const y = idx * barRowHeight;
          const w = (bin.volume / maxBinVolume) * barAreaWidth;
          const midPrice = (bin.priceLow + bin.priceHigh) / 2;
          const isPoc =
            poc != null && midPrice >= bin.priceLow && midPrice <= bin.priceHigh && bin.volume === maxBinVolume;
          return (
            <g key={`${bin.priceLow}-${idx}`}>
              <text
                x={4}
                y={y + barRowHeight / 2 + 3}
                className="fill-slate-400"
                fontSize="9"
                fontFamily="ui-monospace, monospace"
              >
                {midPrice.toFixed(midPrice >= 100 ? 1 : 2)}
              </text>
              <rect
                x={labelStripWidth}
                y={y + 0.5}
                width={Math.max(1, w)}
                height={Math.max(1, barRowHeight - 1)}
                className={
                  isPoc
                    ? "fill-bergt-green/70"
                    : "fill-slate-500/40"
                }
              />
            </g>
          );
        })}
      </svg>
      <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-500">
        bins: {profile.bins.length} · total volume:{" "}
        {formatLarge(profile.totalVolume)}
      </p>
    </section>
  );
}

function formatLarge(value: number): string {
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toFixed(0);
}
