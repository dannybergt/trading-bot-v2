import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

export type ChartCandle = {
  time: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  sma_20: number | null;
  sma_50: number | null;
  sma_100: number | null;
  sma_200: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  bb_mid: number | null;
  ema_12: number | null;
  ema_26: number | null;
  atr: number | null;
  vwap: number | null;
  stoch_k: number | null;
  stoch_d: number | null;
};

export type ChartPattern = {
  name: string;
  signal: "buy" | "sell" | "neutral";
  timestamp: string;
};

export type ChartZones = {
  direction: "UP" | "DOWN";
  currentPrice: number;
  atr: number;
  entryLow: number;
  entryHigh: number;
  stopLoss: number;
  target: number;
  riskReward: number | null;
};

type OverlayKey =
  | "sma_20"
  | "sma_50"
  | "sma_200"
  | "ema_12"
  | "ema_26"
  | "vwap"
  | "bollinger";

const OVERLAY_DEFS: Array<{
  key: OverlayKey;
  label: string;
  color: string;
  defaultOn: boolean;
}> = [
  { key: "sma_20", label: "SMA 20", color: "#22c55e", defaultOn: true },
  { key: "sma_50", label: "SMA 50", color: "#0ea5e9", defaultOn: false },
  { key: "sma_200", label: "SMA 200", color: "#f97316", defaultOn: false },
  { key: "ema_12", label: "EMA 12", color: "#a78bfa", defaultOn: false },
  { key: "ema_26", label: "EMA 26", color: "#f472b6", defaultOn: false },
  { key: "vwap", label: "VWAP", color: "#facc15", defaultOn: true },
  { key: "bollinger", label: "Bollinger", color: "#94a3b8", defaultOn: false },
];

type SubPaneKey = "rsi" | "macd";

const SUB_PANE_DEFS: Array<{ key: SubPaneKey; label: string }> = [
  { key: "rsi", label: "RSI 14" },
  { key: "macd", label: "MACD 12-26-9" },
];

function toTime(value: string): UTCTimestamp {
  // Backend formats either "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" (intraday).
  const iso = value.includes("T") ? value : value.replace(" ", "T") + ":00Z";
  const ms = Date.parse(iso.endsWith("Z") ? iso : `${iso}Z`);
  return Math.floor(ms / 1000) as UTCTimestamp;
}

function pickLine(
  candles: ChartCandle[],
  field: keyof ChartCandle,
): Array<{ time: UTCTimestamp; value: number }> {
  const out: Array<{ time: UTCTimestamp; value: number }> = [];
  for (const c of candles) {
    const v = c[field];
    if (typeof v === "number" && Number.isFinite(v)) {
      out.push({ time: toTime(c.time), value: v });
    }
  }
  return out;
}

function patternMarkers(patterns: ChartPattern[]): SeriesMarker<Time>[] {
  return patterns.map((p) => {
    const time = toTime(p.timestamp);
    if (p.signal === "buy") {
      return {
        time,
        position: "belowBar",
        color: "#22c55e",
        shape: "arrowUp",
        text: p.name,
      };
    }
    if (p.signal === "sell") {
      return {
        time,
        position: "aboveBar",
        color: "#ef4444",
        shape: "arrowDown",
        text: p.name,
      };
    }
    return {
      time,
      position: "inBar",
      color: "#94a3b8",
      shape: "circle",
      text: p.name,
    };
  });
}

export function StockChart({
  candles,
  patterns,
  zones,
}: {
  candles: ChartCandle[];
  patterns: ChartPattern[];
  zones?: ChartZones | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rsiRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdHistRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const overlayRefs = useRef<Map<OverlayKey, ISeriesApi<"Line">>>(new Map());
  const bollingerRefs = useRef<{
    upper?: ISeriesApi<"Line">;
    lower?: ISeriesApi<"Line">;
  }>({});
  const markerPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const zoneLinesRef = useRef<IPriceLine[]>([]);
  const [showZones, setShowZones] = useState(true);

  const [enabledOverlays, setEnabledOverlays] = useState<Set<OverlayKey>>(() => {
    const s = new Set<OverlayKey>();
    for (const o of OVERLAY_DEFS) {
      if (o.defaultOn) s.add(o.key);
    }
    return s;
  });
  const [enabledSubPanes, setEnabledSubPanes] = useState<Set<SubPaneKey>>(
    () => new Set<SubPaneKey>(["rsi"]),
  );

  // Create the chart once.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#020617" },
        textColor: "#cbd5e1",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      timeScale: {
        borderColor: "#1e293b",
        timeVisible: true,
      },
      rightPriceScale: { borderColor: "#1e293b" },
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: true,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    const volumeSeries = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      },
      1,
    );
    chart
      .panes()[1]
      ?.priceScale("volume")
      .applyOptions({ scaleMargins: { top: 0.7, bottom: 0 } });

    chartRef.current = chart;
    candleRef.current = candleSeries;
    volumeRef.current = volumeSeries;

    const handleResize = () => chart.applyOptions({ autoSize: true });
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      rsiRef.current = null;
      macdLineRef.current = null;
      macdSignalRef.current = null;
      macdHistRef.current = null;
      overlayRefs.current.clear();
      bollingerRefs.current = {};
      markerPluginRef.current = null;
    };
  }, []);

  // Push candle/volume data whenever the input changes.
  useEffect(() => {
    if (!candleRef.current || !volumeRef.current) return;
    const candleData = candles
      .filter((c) => c.open != null && c.high != null && c.low != null && c.close != null)
      .map((c) => ({
        time: toTime(c.time),
        open: c.open as number,
        high: c.high as number,
        low: c.low as number,
        close: c.close as number,
      }));
    const volumeData = candles.map((c) => ({
      time: toTime(c.time),
      value: c.volume,
      color:
        (c.close ?? 0) >= (c.open ?? 0)
          ? "rgba(34, 197, 94, 0.5)"
          : "rgba(239, 68, 68, 0.5)",
    }));
    candleRef.current.setData(candleData);
    volumeRef.current.setData(volumeData);

    if (markerPluginRef.current) {
      markerPluginRef.current.setMarkers(patternMarkers(patterns));
    } else if (candleRef.current) {
      markerPluginRef.current = createSeriesMarkers(
        candleRef.current,
        patternMarkers(patterns),
      );
    }
    chartRef.current?.timeScale().fitContent();
  }, [candles, patterns]);

  // Manage overlay series (SMA / EMA / VWAP / Bollinger).
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const def of OVERLAY_DEFS) {
      const wanted = enabledOverlays.has(def.key);
      if (def.key === "bollinger") {
        if (wanted && !bollingerRefs.current.upper) {
          bollingerRefs.current.upper = chart.addSeries(LineSeries, {
            color: def.color,
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          bollingerRefs.current.lower = chart.addSeries(LineSeries, {
            color: def.color,
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          bollingerRefs.current.upper.setData(pickLine(candles, "bb_upper"));
          bollingerRefs.current.lower.setData(pickLine(candles, "bb_lower"));
        } else if (!wanted && bollingerRefs.current.upper) {
          chart.removeSeries(bollingerRefs.current.upper);
          if (bollingerRefs.current.lower) chart.removeSeries(bollingerRefs.current.lower);
          bollingerRefs.current = {};
        } else if (wanted && bollingerRefs.current.upper) {
          bollingerRefs.current.upper.setData(pickLine(candles, "bb_upper"));
          bollingerRefs.current.lower?.setData(pickLine(candles, "bb_lower"));
        }
        continue;
      }

      const existing = overlayRefs.current.get(def.key);
      if (wanted && !existing) {
        const series = chart.addSeries(LineSeries, {
          color: def.color,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          title: def.label,
        });
        series.setData(pickLine(candles, def.key));
        overlayRefs.current.set(def.key, series);
      } else if (!wanted && existing) {
        chart.removeSeries(existing);
        overlayRefs.current.delete(def.key);
      } else if (wanted && existing) {
        existing.setData(pickLine(candles, def.key));
      }
    }
  }, [candles, enabledOverlays]);

  // Manage zone price lines (entry / stop / target).
  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;

    for (const line of zoneLinesRef.current) {
      series.removePriceLine(line);
    }
    zoneLinesRef.current = [];

    if (!showZones || !zones) return;

    const directionUp = zones.direction === "UP";
    zoneLinesRef.current.push(
      series.createPriceLine({
        price: zones.entryLow,
        color: directionUp ? "#22c55e" : "#ef4444",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: directionUp ? "Entry low" : "Entry high",
      }),
      series.createPriceLine({
        price: zones.entryHigh,
        color: directionUp ? "#22c55e" : "#ef4444",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: directionUp ? "Entry high" : "Entry low",
      }),
      series.createPriceLine({
        price: zones.stopLoss,
        color: "#ef4444",
        lineWidth: 1,
        lineStyle: 0,
        axisLabelVisible: true,
        title: "Stop",
      }),
      series.createPriceLine({
        price: zones.target,
        color: "#22c55e",
        lineWidth: 1,
        lineStyle: 0,
        axisLabelVisible: true,
        title: "Target",
      }),
    );
  }, [zones, showZones, candles]);

  // Manage sub-panes (RSI, MACD).
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const wantRsi = enabledSubPanes.has("rsi");
    const wantMacd = enabledSubPanes.has("macd");

    // Pane index 0: price, 1: volume, 2+: indicators (in order)
    let nextPaneIndex = 2;

    if (wantRsi && !rsiRef.current) {
      rsiRef.current = chart.addSeries(
        LineSeries,
        { color: "#a78bfa", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "RSI" },
        nextPaneIndex,
      );
      rsiRef.current.setData(pickLine(candles, "rsi"));
      nextPaneIndex += 1;
    } else if (!wantRsi && rsiRef.current) {
      chart.removeSeries(rsiRef.current);
      rsiRef.current = null;
    } else if (wantRsi && rsiRef.current) {
      rsiRef.current.setData(pickLine(candles, "rsi"));
      nextPaneIndex += 1;
    } else if (wantRsi) {
      nextPaneIndex += 1;
    }

    if (wantMacd && !macdLineRef.current) {
      macdLineRef.current = chart.addSeries(
        LineSeries,
        { color: "#22c55e", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "MACD" },
        nextPaneIndex,
      );
      macdSignalRef.current = chart.addSeries(
        LineSeries,
        { color: "#ef4444", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "Signal" },
        nextPaneIndex,
      );
      macdHistRef.current = chart.addSeries(
        HistogramSeries,
        { color: "#64748b", priceLineVisible: false, lastValueVisible: false, title: "Hist" },
        nextPaneIndex,
      );
      macdLineRef.current.setData(pickLine(candles, "macd"));
      macdSignalRef.current.setData(pickLine(candles, "macd_signal"));
      macdHistRef.current.setData(
        pickLine(candles, "macd_hist").map((p) => ({
          time: p.time,
          value: p.value,
          color: p.value >= 0 ? "rgba(34, 197, 94, 0.6)" : "rgba(239, 68, 68, 0.6)",
        })),
      );
    } else if (!wantMacd && macdLineRef.current) {
      if (macdLineRef.current) chart.removeSeries(macdLineRef.current);
      if (macdSignalRef.current) chart.removeSeries(macdSignalRef.current);
      if (macdHistRef.current) chart.removeSeries(macdHistRef.current);
      macdLineRef.current = null;
      macdSignalRef.current = null;
      macdHistRef.current = null;
    } else if (wantMacd && macdLineRef.current) {
      macdLineRef.current.setData(pickLine(candles, "macd"));
      macdSignalRef.current?.setData(pickLine(candles, "macd_signal"));
      macdHistRef.current?.setData(
        pickLine(candles, "macd_hist").map((p) => ({
          time: p.time,
          value: p.value,
          color: p.value >= 0 ? "rgba(34, 197, 94, 0.6)" : "rgba(239, 68, 68, 0.6)",
        })),
      );
    }
  }, [candles, enabledSubPanes]);

  const overlayButtons = useMemo(() => OVERLAY_DEFS, []);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-400">Overlays:</span>
        {overlayButtons.map((def) => {
          const active = enabledOverlays.has(def.key);
          return (
            <button
              key={def.key}
              type="button"
              onClick={() =>
                setEnabledOverlays((prev) => {
                  const next = new Set(prev);
                  if (active) next.delete(def.key);
                  else next.add(def.key);
                  return next;
                })
              }
              className={`rounded-full border px-2 py-0.5 transition ${
                active
                  ? "border-bergt-green/50 bg-bergt-green/10 text-bergt-green"
                  : "border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-500"
              }`}
              style={active ? { color: def.color, borderColor: `${def.color}66` } : undefined}
            >
              {def.label}
            </button>
          );
        })}
        {zones ? (
          <>
            <span className="ml-2 text-slate-400">Zones:</span>
            <button
              type="button"
              onClick={() => setShowZones((v) => !v)}
              className={`rounded-full border px-2 py-0.5 transition ${
                showZones
                  ? "border-bergt-green/50 bg-bergt-green/10 text-bergt-green"
                  : "border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-500"
              }`}
            >
              {showZones ? "Hide" : "Show"} entry/stop/target
            </button>
          </>
        ) : null}
        <span className="ml-2 text-slate-400">Panes:</span>
        {SUB_PANE_DEFS.map((def) => {
          const active = enabledSubPanes.has(def.key);
          return (
            <button
              key={def.key}
              type="button"
              onClick={() =>
                setEnabledSubPanes((prev) => {
                  const next = new Set(prev);
                  if (active) next.delete(def.key);
                  else next.add(def.key);
                  return next;
                })
              }
              className={`rounded-full border px-2 py-0.5 transition ${
                active
                  ? "border-bergt-green/50 bg-bergt-green/10 text-bergt-green"
                  : "border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-500"
              }`}
            >
              {def.label}
            </button>
          );
        })}
      </div>
      <div
        ref={containerRef}
        className="h-[560px] w-full rounded-lg border border-slate-800 bg-slate-950"
      />
    </div>
  );
}
